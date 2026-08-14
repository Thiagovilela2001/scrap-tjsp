from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Sequence

from .client import TJSPClient
from .models import Consulta, Decisao


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tjsp-jurisprudencia",
        description="Coleta jurisprudência pública do TJSP/CJSG.",
    )
    parser.add_argument("pesquisa", nargs="?", default="", help="Pesquisa livre no inteiro teor.")
    parser.add_argument("--ementa", default="", help="Texto buscado somente na ementa.")
    parser.add_argument("--classe", default="", help="ID interno da classe no TJSP.")
    parser.add_argument("--assunto", default="", help="ID interno do assunto no TJSP.")
    parser.add_argument("--comarca", default="", help="ID interno da comarca no TJSP.")
    parser.add_argument("--orgao-julgador", default="", help="ID interno do órgão julgador.")
    parser.add_argument("--inicio", default="", help="Data inicial do julgamento: DD/MM/AAAA.")
    parser.add_argument("--fim", default="", help="Data final do julgamento: DD/MM/AAAA.")
    parser.add_argument(
        "--origem",
        choices=("segundo_grau", "colegio_recursal"),
        default="segundo_grau",
    )
    parser.add_argument(
        "--tipo",
        choices=("acordao", "homologacao", "monocratica"),
        default="acordao",
    )
    parser.add_argument("--sem-sinonimos", action="store_true")
    parser.add_argument("--paginas", type=int, default=1, help="Máximo de páginas; padrão: 1.")
    parser.add_argument("--intervalo", type=float, default=2.0, help="Segundos entre requisições.")
    parser.add_argument(
        "--saida",
        type=Path,
        default=Path("output/resultados.jsonl"),
        help="Arquivo .jsonl ou .csv.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    consulta = Consulta(
        pesquisa=args.pesquisa,
        ementa=args.ementa,
        classe=args.classe,
        assunto=args.assunto,
        comarca=args.comarca,
        orgao_julgador=args.orgao_julgador,
        data_julgamento_inicio=args.inicio,
        data_julgamento_fim=args.fim,
        origem=args.origem,
        tipo_decisao=args.tipo,
        pesquisar_sinonimos=not args.sem_sinonimos,
    )
    cliente = TJSPClient(intervalo=args.intervalo)
    resultado = cliente.pesquisar(consulta, max_paginas=args.paginas)
    _salvar(args.saida, resultado.decisoes)
    print(
        f"Disponíveis: {resultado.total_disponivel}; "
        f"coletados: {len(resultado.decisoes)}; "
        f"páginas: {resultado.paginas_coletadas}; saída: {args.saida}"
    )
    return 0


def _salvar(caminho: Path, decisoes: Sequence[Decisao]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    sufixo = caminho.suffix.casefold()
    if sufixo == ".jsonl":
        with caminho.open("w", encoding="utf-8", newline="\n") as arquivo:
            for decisao in decisoes:
                arquivo.write(json.dumps(decisao.como_dict(), ensure_ascii=False) + "\n")
        return
    if sufixo == ".csv":
        linhas = [decisao.como_dict() for decisao in decisoes]
        campos = list(Decisao.__dataclass_fields__)
        with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=campos)
            escritor.writeheader()
            escritor.writerows(linhas)
        return
    raise ValueError("Saída deve terminar em .jsonl ou .csv.")


if __name__ == "__main__":
    raise SystemExit(main())
