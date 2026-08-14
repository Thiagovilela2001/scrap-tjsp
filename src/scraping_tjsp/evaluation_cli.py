from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from dotenv import load_dotenv

from .cost import PrecosTokens, estimar_custo_maximo, resumir_custo
from .evaluation import AvaliadorJuridico, JuizJuridicoIA, carregar_casos
from .maritaca import ErroMaritaca, ProvedorMaritaca
from .rag import PacoteContextoIA, PreparadorContextoIA, RespostaIA
from .search import BuscaHibrida
from .storage import RepositorioSQLite
from .vector_store import RepositorioChunksChroma


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tjsp-avaliar",
        description="Avalia recuperação, citações e respostas jurídicas do pipeline.",
    )
    parser.add_argument("dataset", type=Path, help="Casos de avaliação em JSONL.")
    parser.add_argument(
        "--max-casos",
        type=int,
        default=None,
        help="Avalia somente os primeiros N casos do dataset.",
    )
    parser.add_argument("--limite", type=int, default=6)
    parser.add_argument("--max-caracteres", type=int, default=12_000)
    parser.add_argument("--sqlite-path", type=Path, default=Path("data/tjsp.sqlite3"))
    parser.add_argument("--chroma-path", type=Path, default=Path("data/chroma"))
    parser.add_argument("--saida", type=Path, default=Path("output/avaliacao.json"))
    parser.add_argument(
        "--gerar-respostas",
        action="store_true",
        help="Gera respostas com Maritaca; pode gerar cobrança.",
    )
    parser.add_argument(
        "--juiz-ia",
        action="store_true",
        help="Usa segunda chamada Maritaca como juiz; pode gerar cobrança.",
    )
    parser.add_argument("--modelo", default=None)
    parser.add_argument("--max-output-tokens", type=int, default=2_000)
    parser.add_argument(
        "--max-custo-brl",
        type=float,
        default=None,
        help="Teto conservador antes das chamadas; requer --gerar-respostas.",
    )
    parser.add_argument("--preco-entrada-milhao", type=float, default=5.0)
    parser.add_argument("--preco-saida-milhao", type=float, default=20.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)
    if args.juiz_ia and not args.gerar_respostas:
        parser.error("--juiz-ia exige --gerar-respostas.")
    if args.max_casos is not None and args.max_casos < 1:
        parser.error("--max-casos deve ser pelo menos 1.")
    if args.max_output_tokens < 1:
        parser.error("--max-output-tokens deve ser pelo menos 1.")
    if args.max_custo_brl is not None and args.max_custo_brl <= 0:
        parser.error("--max-custo-brl deve ser positivo.")
    if args.max_custo_brl is not None and not args.gerar_respostas:
        parser.error("--max-custo-brl exige --gerar-respostas.")
    if args.max_custo_brl is not None and args.juiz_ia:
        parser.error("--max-custo-brl ainda não suporta --juiz-ia.")
    try:
        precos = PrecosTokens(
            entrada_milhao=args.preco_entrada_milhao,
            saida_milhao=args.preco_saida_milhao,
        )
    except ValueError as exc:
        parser.error(str(exc))
    load_dotenv()
    casos = carregar_casos(args.dataset)
    if args.max_casos is not None:
        casos = casos[: args.max_casos]
    sqlite = RepositorioSQLite(args.sqlite_path)
    sqlite.inicializar()
    preparador = PreparadorContextoIA(
        BuscaHibrida(sqlite, RepositorioChunksChroma(args.chroma_path))
    )
    avaliador = AvaliadorJuridico()
    juiz = JuizJuridicoIA()
    casos_pacotes = [
        (
            caso,
            preparador.preparar(
                caso.pergunta,
                limite_fontes=args.limite,
                max_caracteres=args.max_caracteres,
                filtros=caso.filtros,
            ),
        )
        for caso in casos
    ]
    estimativa_maxima = None
    if args.gerar_respostas and not args.juiz_ia:
        estimativa_maxima = estimar_custo_maximo(
            [pacote for _, pacote in casos_pacotes],
            max_output_tokens=args.max_output_tokens,
            precos=precos,
        )
        if args.max_custo_brl is not None and estimativa_maxima > args.max_custo_brl:
            parser.error(
                "Estimativa conservadora de "
                f"R$ {estimativa_maxima:.4f} excede o teto de "
                f"R$ {args.max_custo_brl:.4f}; nenhuma chamada foi feita."
            )
    provedor = _provedor(args, parser) if args.gerar_respostas else None
    resultados = []
    respostas_cobradas = []

    for caso, pacote in casos_pacotes:
        resposta = None
        resultado_juiz = None
        erros = []
        auditorias = []
        if provedor:
            resposta, erro, execucao_id = _responder_auditado(
                sqlite,
                provedor,
                pacote,
                tipo="avaliacao_resposta",
                caso_id=caso.caso_id,
                args=args,
            )
            auditorias.append(
                {"tipo": "avaliacao_resposta", "execucao_ia_id": execucao_id}
            )
            if erro:
                erros.append(erro)
            elif resposta:
                respostas_cobradas.append(resposta)
        if args.juiz_ia and provedor and resposta:
            pacote_juiz = juiz.preparar(caso, pacote, resposta)
            resposta_juiz, erro, execucao_id = _responder_auditado(
                sqlite,
                provedor,
                pacote_juiz,
                tipo="avaliacao_juiz",
                caso_id=caso.caso_id,
                args=args,
            )
            auditorias.append({"tipo": "avaliacao_juiz", "execucao_ia_id": execucao_id})
            if erro:
                erros.append(erro)
            elif resposta_juiz:
                respostas_cobradas.append(resposta_juiz)
                try:
                    resultado_juiz = juiz.interpretar(resposta_juiz)
                except ValueError as exc:
                    erros.append(str(exc))
        resultado = avaliador.avaliar(
            caso,
            pacote,
            resposta=resposta,
            juiz=resultado_juiz,
            erro="; ".join(erros),
        )
        resultado["auditorias_ia"] = auditorias
        resultados.append(resultado)

    relatorio = avaliador.relatorio(resultados)
    custos = resumir_custo(
        respostas_cobradas,
        precos=precos,
        estimativa_maxima=estimativa_maxima,
        limite_brl=args.max_custo_brl,
    )
    relatorio["custos"] = custos
    relatorio["resumo"]["custo_padrao_estimado_brl"] = custos[
        "custo_padrao_estimado_brl"
    ]
    configuracao = {
        "max_casos": args.max_casos,
        "limite": args.limite,
        "max_caracteres": args.max_caracteres,
        "gerar_respostas": args.gerar_respostas,
        "juiz_ia": args.juiz_ia,
        "modelo": provedor.modelo if provedor else None,
        "max_custo_brl": args.max_custo_brl,
        "preco_entrada_milhao": precos.entrada_milhao,
        "preco_saida_milhao": precos.saida_milhao,
    }
    avaliacao_id = sqlite.registrar_avaliacao(
        relatorio,
        dataset=str(args.dataset),
        configuracao=configuracao,
    )
    relatorio["avaliacao_id"] = avaliacao_id
    relatorio["configuracao"] = configuracao
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(relatorio["resumo"], ensure_ascii=False))
    print(f"avaliação_id: {avaliacao_id}; relatório: {args.saida}")
    return 0 if relatorio["resumo"]["aprovado"] else 1


def _provedor(args, parser: argparse.ArgumentParser) -> ProvedorMaritaca:
    try:
        return ProvedorMaritaca(
            modelo=args.modelo,
            max_output_tokens=args.max_output_tokens,
        )
    except ErroMaritaca as exc:
        parser.error(str(exc))


def _responder_auditado(
    sqlite: RepositorioSQLite,
    provedor: ProvedorMaritaca,
    pacote: PacoteContextoIA,
    *,
    tipo: str,
    caso_id: str,
    args,
) -> tuple[RespostaIA | None, str, int]:
    execucao_id = sqlite.iniciar_execucao_ia(
        pacote,
        provedor="maritaca",
        modelo=provedor.modelo,
        configuracao={
            "tipo": tipo,
            "caso_id": caso_id,
            "limite_fontes": args.limite,
            "max_caracteres": args.max_caracteres,
            "max_output_tokens": args.max_output_tokens,
        },
    )
    try:
        resposta = provedor.responder(pacote)
    except ErroMaritaca as exc:
        sqlite.falhar_execucao_ia(
            execucao_id,
            str(exc),
            duracao_ms=exc.duracao_ms,
        )
        return None, str(exc), execucao_id
    sqlite.concluir_execucao_ia(execucao_id, resposta)
    return resposta, "", execucao_id


if __name__ == "__main__":
    raise SystemExit(main())
