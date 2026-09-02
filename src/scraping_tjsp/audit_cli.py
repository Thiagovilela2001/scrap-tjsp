from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .settings import get_settings
from .storage import RepositorioSQLite


def construir_parser() -> argparse.ArgumentParser:
    cfg = get_settings()
    parser = argparse.ArgumentParser(
        prog="tjsp-auditoria",
        description="Consulta a trilha SQLite das chamadas de inteligência artificial.",
    )
    parser.add_argument("execucao_id", nargs="?", type=int)
    parser.add_argument("--limite", type=int, default=20)
    parser.add_argument("--sqlite-path", type=Path, default=cfg.sqlite_path)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    repositorio = RepositorioSQLite(args.sqlite_path)
    repositorio.inicializar()
    if args.execucao_id is not None:
        dados = repositorio.obter_execucao_ia(args.execucao_id)
    else:
        dados = repositorio.listar_execucoes_ia(limite=args.limite)
    if args.json or args.execucao_id is not None:
        print(json.dumps(dados, ensure_ascii=False, indent=2))
        return 0
    for item in dados:
        print(
            f"{item['id']}: {item['status']} | {item['provedor']}/{item['modelo']} | "
            f"tokens={item['tokens_total'] or '-'} | {item['pergunta']}"
        )
    if not dados:
        print("Nenhuma execução de IA auditada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
