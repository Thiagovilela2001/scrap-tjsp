from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .rag import PreparadorContextoIA
from .search import BuscaHibrida
from .storage import RepositorioSQLite
from .vector_store import RepositorioChunksChroma


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tjsp-busca",
        description="Busca híbrida nos inteiros teores persistidos do TJSP.",
    )
    parser.add_argument("consulta", help="Pergunta ou termos jurídicos.")
    parser.add_argument("--limite", type=int, default=10)
    parser.add_argument("--sqlite-path", type=Path, default=Path("data/tjsp.sqlite3"))
    parser.add_argument("--chroma-path", type=Path, default=Path("data/chroma"))
    parser.add_argument("--cd-acordao", default="")
    parser.add_argument("--processo", default="")
    parser.add_argument("--classe", default="")
    parser.add_argument("--assunto", default="")
    parser.add_argument("--orgao-julgador", default="")
    parser.add_argument("--pagina", type=int)
    parser.add_argument(
        "--contexto-ia",
        action="store_true",
        help="Produz pacote RAG pronto para um provedor de IA.",
    )
    parser.add_argument("--max-caracteres", type=int, default=12_000)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    sqlite = RepositorioSQLite(args.sqlite_path)
    sqlite.inicializar()
    busca = BuscaHibrida(sqlite, RepositorioChunksChroma(args.chroma_path))
    filtros = _filtros(args)

    if args.contexto_ia:
        pacote = PreparadorContextoIA(busca).preparar(
            args.consulta,
            limite_fontes=args.limite,
            max_caracteres=args.max_caracteres,
            filtros=filtros,
        )
        print(json.dumps(pacote.como_dict(), ensure_ascii=False, indent=2))
        return 0

    resultados = busca.buscar(args.consulta, limite=args.limite, filtros=filtros)
    if args.json:
        print(
            json.dumps(
                [resultado.como_dict() for resultado in resultados],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    for posicao, resultado in enumerate(resultados, start=1):
        citacao = resultado.metadata.get("citacao", resultado.id)
        trecho = resultado.texto.replace("\n", " ")[:500]
        print(f"{posicao}. {citacao}")
        print(
            f"   score={resultado.score_hibrido:.6f}; fontes={','.join(resultado.origens)}"
        )
        print(f"   {trecho}")
    if not resultados:
        print("Nenhum resultado encontrado.")
    return 0


def _filtros(args: argparse.Namespace) -> dict[str, str | int]:
    valores = {
        "cd_acordao": args.cd_acordao,
        "processo": args.processo,
        "classe": args.classe,
        "assunto": args.assunto,
        "orgao_julgador": args.orgao_julgador,
        "pagina": args.pagina,
    }
    return {chave: valor for chave, valor in valores.items() if valor not in ("", None)}


if __name__ == "__main__":
    raise SystemExit(main())
