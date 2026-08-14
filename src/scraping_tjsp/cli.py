from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Sequence
from pathlib import Path

from .client import TJSPClient
from .downloader import DownloadPDFError, PDFDownloader
from .models import Consulta, Decisao
from .processor import ProcessadorPDF, ProcessamentoPDFError
from .storage import RepositorioSQLite
from .vector_store import RepositorioChroma, RepositorioChunksChroma


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tjsp-jurisprudencia",
        description="Coleta jurisprudência pública do TJSP/CJSG.",
    )
    parser.add_argument(
        "pesquisa", nargs="?", default="", help="Pesquisa livre no inteiro teor."
    )
    parser.add_argument("--ementa", default="", help="Texto buscado somente na ementa.")
    parser.add_argument("--classe", default="", help="ID interno da classe no TJSP.")
    parser.add_argument("--assunto", default="", help="ID interno do assunto no TJSP.")
    parser.add_argument("--comarca", default="", help="ID interno da comarca no TJSP.")
    parser.add_argument(
        "--orgao-julgador", default="", help="ID interno do órgão julgador."
    )
    parser.add_argument(
        "--inicio", default="", help="Data inicial do julgamento: DD/MM/AAAA."
    )
    parser.add_argument(
        "--fim", default="", help="Data final do julgamento: DD/MM/AAAA."
    )
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
    parser.add_argument(
        "--paginas", type=int, default=1, help="Máximo de páginas; padrão: 1."
    )
    parser.add_argument(
        "--intervalo", type=float, default=2.0, help="Segundos entre requisições."
    )
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=Path("data/tjsp.sqlite3"),
        help="Arquivo SQLite; padrão: data/tjsp.sqlite3.",
    )
    parser.add_argument(
        "--chroma-path",
        type=Path,
        default=Path("data/chroma"),
        help="Diretório Chroma; padrão: data/chroma.",
    )
    parser.add_argument(
        "--sem-persistencia",
        action="store_true",
        help="Desliga SQLite e Chroma; mantém somente JSONL/CSV.",
    )
    parser.add_argument(
        "--baixar-pdfs",
        action="store_true",
        help="Baixa inteiros teores após persistir metadados.",
    )
    parser.add_argument(
        "--max-pdfs",
        type=int,
        default=20,
        help="Limite de PDFs por execução; padrão: 20.",
    )
    parser.add_argument(
        "--diretorio-pdfs",
        type=Path,
        default=Path("data/pdfs"),
    )
    parser.add_argument(
        "--max-mb-pdf",
        type=int,
        default=50,
        help="Tamanho máximo de cada PDF; padrão: 50 MB.",
    )
    parser.add_argument(
        "--processar-pdfs",
        action="store_true",
        help="Extrai texto por p\u00e1gina e indexa chunks dos PDFs baixados.",
    )
    parser.add_argument(
        "--sem-ocr",
        action="store_true",
        help="N\u00e3o tenta OCR em p\u00e1ginas com pouco texto nativo.",
    )
    parser.add_argument(
        "--tamanho-chunk",
        type=int,
        default=1500,
        help="Tamanho m\u00e1ximo aproximado de cada chunk; padr\u00e3o: 1500.",
    )
    parser.add_argument(
        "--sobreposicao-chunk",
        type=int,
        default=200,
        help="Sobreposi\u00e7\u00e3o aproximada entre chunks; padr\u00e3o: 200.",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=Path("output/resultados.jsonl"),
        help="Arquivo .jsonl ou .csv.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    if args.baixar_pdfs and args.max_pdfs < 1:
        raise ValueError("--max-pdfs deve ser pelo menos 1.")
    if args.max_mb_pdf < 1:
        raise ValueError("--max-mb-pdf deve ser pelo menos 1.")
    if args.processar_pdfs and not args.baixar_pdfs:
        raise ValueError("--processar-pdfs exige --baixar-pdfs.")
    if args.processar_pdfs and args.sem_persistencia:
        raise ValueError("--processar-pdfs exige persist\u00eancia SQLite + Chroma.")
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

    repositorio: RepositorioSQLite | None = None
    consulta_id = None
    chroma_indexados = 0
    if not args.sem_persistencia:
        repositorio = RepositorioSQLite(args.sqlite_path)
        repositorio.inicializar()
        consulta_id = repositorio.salvar_pesquisa(consulta, resultado)
        chroma_indexados = RepositorioChroma(args.chroma_path).indexar_decisoes(
            resultado.decisoes
        )

    baixados = 0
    reutilizados = 0
    erros_pdf = 0
    processados = 0
    erros_processamento = 0
    chunks_indexados = 0
    if args.baixar_pdfs:
        downloader = PDFDownloader(
            cliente,
            diretorio=args.diretorio_pdfs,
            limite_bytes=args.max_mb_pdf * 1024 * 1024,
        )
        processador = None
        repositorio_chunks = None
        if args.processar_pdfs:
            processador = ProcessadorPDF(
                tamanho_chunk=args.tamanho_chunk,
                sobreposicao=args.sobreposicao_chunk,
                habilitar_ocr=not args.sem_ocr,
            )
            repositorio_chunks = RepositorioChunksChroma(args.chroma_path)
        for decisao in resultado.decisoes[: args.max_pdfs]:
            try:
                documento = downloader.baixar(decisao)
                baixados += 1
                reutilizados += int(documento.reutilizado)
                if repositorio:
                    repositorio.registrar_documento(documento)
            except DownloadPDFError as exc:
                erros_pdf += 1
                if repositorio:
                    repositorio.registrar_erro_download(
                        decisao.cd_acordao,
                        decisao.inteiro_teor_url,
                        str(exc),
                    )
                continue

            if processador and repositorio and repositorio_chunks:
                repositorio.iniciar_processamento(decisao.cd_acordao)
                try:
                    processamento = processador.processar(documento)
                    repositorio.registrar_processamento(processamento)
                    chunks_indexados += repositorio_chunks.indexar(
                        processamento, decisao
                    )
                    processados += 1
                except ProcessamentoPDFError as exc:
                    erros_processamento += 1
                    repositorio.registrar_erro_processamento(
                        decisao.cd_acordao, str(exc)
                    )

    print(
        f"Disponíveis: {resultado.total_disponivel}; "
        f"coletados: {len(resultado.decisoes)}; "
        f"páginas: {resultado.paginas_coletadas}; "
        f"PDFs: {baixados} ({reutilizados} reutilizados), erros: {erros_pdf}; "
        f"processados: {processados}, erros: {erros_processamento}, "
        f"chunks: {chunks_indexados}; "
        f"consulta_id: {consulta_id or '-'}; Chroma: {chroma_indexados}; "
        f"saída: {args.saida}"
    )
    return 0


def _salvar(caminho: Path, decisoes: Sequence[Decisao]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    sufixo = caminho.suffix.casefold()
    if sufixo == ".jsonl":
        with caminho.open("w", encoding="utf-8", newline="\n") as arquivo:
            for decisao in decisoes:
                arquivo.write(
                    json.dumps(decisao.como_dict(), ensure_ascii=False) + "\n"
                )
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
