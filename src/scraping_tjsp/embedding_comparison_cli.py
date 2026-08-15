from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

METRICAS = (
    "taxa_aprovacao",
    "recall_medio",
    "mrr_medio",
    "cobertura_termos_contexto_media",
)


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tjsp-comparar-embeddings",
        description="Compara dois relatórios locais gerados por tjsp-avaliar.",
    )
    parser.add_argument("relatorio_base", type=Path)
    parser.add_argument("relatorio_candidato", type=Path)
    parser.add_argument(
        "--saida",
        type=Path,
        default=Path("output/comparacao-embeddings.json"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    base = _carregar(args.relatorio_base)
    candidato = _carregar(args.relatorio_candidato)
    resultado = comparar_relatorios(base, candidato)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(resultado["deltas_candidato_menos_base"], ensure_ascii=False))
    print(f"comparação: {args.saida}")
    return 0


def comparar_relatorios(base: dict, candidato: dict) -> dict:
    resumo_base = _resumo(base)
    resumo_candidato = _resumo(candidato)
    metricas_base = _metricas(resumo_base)
    metricas_candidato = _metricas(resumo_candidato)
    return {
        "base": {
            "embedding_model": _modelo(base),
            "metricas": metricas_base,
        },
        "candidato": {
            "embedding_model": _modelo(candidato),
            "metricas": metricas_candidato,
        },
        "deltas_candidato_menos_base": {
            metrica: round(metricas_candidato[metrica] - metricas_base[metrica], 6)
            for metrica in METRICAS
        },
    }


def _carregar(caminho: Path) -> dict:
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Relatório inválido {caminho}: {exc}") from exc
    if not isinstance(dados, dict):
        raise SystemExit(f"Relatório inválido {caminho}: raiz deve ser objeto JSON.")
    return dados


def _resumo(relatorio: dict) -> dict:
    resumo = relatorio.get("resumo")
    if not isinstance(resumo, dict):
        raise ValueError("Relatório não contém resumo válido.")
    return resumo


def _metricas(resumo: dict) -> dict[str, float]:
    try:
        return {metrica: float(resumo[metrica]) for metrica in METRICAS}
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Relatório não contém métricas comparáveis: {exc}") from exc


def _modelo(relatorio: dict) -> str:
    configuracao = relatorio.get("configuracao") or {}
    return str(configuracao.get("embedding_model") or "não informado")


if __name__ == "__main__":
    raise SystemExit(main())
