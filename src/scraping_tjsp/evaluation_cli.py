from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from dotenv import load_dotenv

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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)
    if args.juiz_ia and not args.gerar_respostas:
        parser.error("--juiz-ia exige --gerar-respostas.")
    load_dotenv()
    casos = carregar_casos(args.dataset)
    sqlite = RepositorioSQLite(args.sqlite_path)
    sqlite.inicializar()
    preparador = PreparadorContextoIA(
        BuscaHibrida(sqlite, RepositorioChunksChroma(args.chroma_path))
    )
    avaliador = AvaliadorJuridico()
    juiz = JuizJuridicoIA()
    provedor = _provedor(args, parser) if args.gerar_respostas else None
    resultados = []

    for caso in casos:
        pacote = preparador.preparar(
            caso.pergunta,
            limite_fontes=args.limite,
            max_caracteres=args.max_caracteres,
            filtros=caso.filtros,
        )
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
    configuracao = {
        "limite": args.limite,
        "max_caracteres": args.max_caracteres,
        "gerar_respostas": args.gerar_respostas,
        "juiz_ia": args.juiz_ia,
        "modelo": provedor.modelo if provedor else None,
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
