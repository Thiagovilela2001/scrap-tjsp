from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from .client import TJSPClient
from .dataset import PreparadorDataset, carregar_fontes_dataset
from .downloader import PDFDownloader
from .evaluation_cli import main as avaliar
from .processor import ProcessadorPDF
from .settings import get_settings
from .storage import RepositorioSQLite
from .vector_store import MODELO_EMBEDDING_PADRAO, RepositorioChunksChroma


def construir_parser() -> argparse.ArgumentParser:
    cfg = get_settings()
    parser = argparse.ArgumentParser(
        prog="tjsp-preparar-dataset",
        description="Baixa, processa, indexa e avalia fontes exatas de um dataset.",
    )
    parser.add_argument("dataset", type=Path, help="Dataset jurídico em JSONL.")
    parser.add_argument("--intervalo", type=float, default=cfg.intervalo_tjsp)
    parser.add_argument("--max-fontes", type=int, default=None)
    parser.add_argument("--sqlite-path", type=Path, default=cfg.sqlite_path)
    parser.add_argument("--chroma-path", type=Path, default=cfg.chroma_path)
    parser.add_argument("--embedding-model", default=MODELO_EMBEDDING_PADRAO)
    parser.add_argument("--diretorio-pdfs", type=Path, default=cfg.diretorio_pdfs)
    parser.add_argument("--max-mb-pdf", type=int, default=cfg.max_mb_pdf)
    parser.add_argument("--sem-ocr", action="store_true")
    parser.add_argument("--tamanho-chunk", type=int, default=cfg.tamanho_chunk)
    parser.add_argument(
        "--sobreposicao-chunk", type=int, default=cfg.sobreposicao_chunk
    )
    parser.add_argument(
        "--sem-avaliacao",
        action="store_true",
        help="Prepara as fontes sem executar tjsp-avaliar ao final.",
    )
    parser.add_argument(
        "--saida-avaliacao",
        type=Path,
        default=Path("output/avaliacao.json"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)
    if args.max_fontes is not None and args.max_fontes < 1:
        parser.error("--max-fontes deve ser pelo menos 1.")
    if args.max_mb_pdf < 1:
        parser.error("--max-mb-pdf deve ser pelo menos 1.")

    fontes = carregar_fontes_dataset(args.dataset)
    if (
        args.max_fontes is not None
        and args.max_fontes < len(fontes)
        and not args.sem_avaliacao
    ):
        parser.error("Preparação parcial com --max-fontes exige --sem-avaliacao.")

    cliente = TJSPClient(intervalo=args.intervalo)
    resultado = PreparadorDataset(
        RepositorioSQLite(args.sqlite_path),
        PDFDownloader(
            cliente,
            diretorio=args.diretorio_pdfs,
            limite_bytes=args.max_mb_pdf * 1024 * 1024,
        ),
        ProcessadorPDF(
            tamanho_chunk=args.tamanho_chunk,
            sobreposicao=args.sobreposicao_chunk,
            habilitar_ocr=not args.sem_ocr,
        ),
        RepositorioChunksChroma(
            args.chroma_path,
            modelo_embedding=args.embedding_model,
        ),
    ).preparar(
        fontes,
        nome_dataset=args.dataset.name,
        limite=args.max_fontes,
    )
    print(
        f"Fontes: {resultado.total_fontes}; "
        f"PDFs: {resultado.baixados} ({resultado.reutilizados} reutilizados), "
        f"erros: {resultado.erros_download}; "
        f"processados: {resultado.processados}, "
        f"erros: {resultado.erros_processamento}; "
        f"chunks: {resultado.chunks_indexados}"
    )
    if not resultado.aprovado:
        return 1
    if args.sem_avaliacao:
        return 0
    return avaliar(
        [
            str(args.dataset),
            "--sqlite-path",
            str(args.sqlite_path),
            "--chroma-path",
            str(args.chroma_path),
            "--saida",
            str(args.saida_avaliacao),
            "--embedding-model",
            args.embedding_model,
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
