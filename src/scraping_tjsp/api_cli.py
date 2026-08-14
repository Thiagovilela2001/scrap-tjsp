from __future__ import annotations

import argparse
from collections.abc import Sequence

import uvicorn


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tjsp-api",
        description="Inicia a API local de busca e respostas sobre jurisprudência.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--porta", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    if not 1 <= args.porta <= 65_535:
        raise SystemExit("A porta deve estar entre 1 e 65535.")
    uvicorn.run(
        "scraping_tjsp.api:criar_app",
        factory=True,
        host=args.host,
        port=args.porta,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
