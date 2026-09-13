from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api_routes_ia import criar_router_ia
from .api_routes_juris import criar_router_juris
from .api_schemas import (
    ConfiguracaoAPI,
    FiltrosBusca,
    RequisicaoAnaliseDocumental,
    RequisicaoBusca,
    RequisicaoImportacaoTJSP,
    RequisicaoMinuta,
    RequisicaoPergunta,
    RequisicaoPesquisaAssistida,
    RequisicaoPesquisaTJSP,
)
from .assisted_research import PesquisaAssistidaTJSP
from .client import TJSPClient
from .cost import PrecosTokens
from .document_analysis import AnaliseDocumentalTJSP
from .downloader import PDFDownloader
from .ingestion import ServicoColetaTJSP
from .maritaca import ProvedorMaritaca
from .processor import ProcessadorPDF
from .rag import PreparadorContextoIA, ProvedorIA
from .search import BuscaHibrida
from .storage import RepositorioSQLite
from .vector_store import RepositorioChroma, RepositorioChunksChroma

__all__ = [
    "ConfiguracaoAPI",
    "FiltrosBusca",
    "RequisicaoAnaliseDocumental",
    "RequisicaoBusca",
    "RequisicaoImportacaoTJSP",
    "RequisicaoMinuta",
    "RequisicaoPergunta",
    "RequisicaoPesquisaAssistida",
    "RequisicaoPesquisaTJSP",
    "criar_app",
]


class ProvedorConfigurado(ProvedorIA, Protocol):
    modelo: str


ProvedorFactory = Callable[[str | None, int], ProvedorConfigurado]
WEB_DIR = Path(__file__).with_name("web")


def _criar_provedor_maritaca(
    modelo: str | None,
    max_output_tokens: int,
) -> ProvedorMaritaca:
    return ProvedorMaritaca(
        modelo=modelo,
        max_output_tokens=max_output_tokens,
    )


def criar_app(
    *,
    configuracao: ConfiguracaoAPI | None = None,
    repositorio: RepositorioSQLite | None = None,
    repositorio_chunks: RepositorioChunksChroma | None = None,
    busca: BuscaHibrida | None = None,
    provedor_factory: ProvedorFactory | None = None,
    servico_tjsp: ServicoColetaTJSP | None = None,
    pesquisa_assistida: PesquisaAssistidaTJSP | None = None,
    analise_documental: AnaliseDocumentalTJSP | None = None,
) -> FastAPI:
    load_dotenv()
    config = configuracao or ConfiguracaoAPI.do_ambiente()
    sqlite = repositorio or RepositorioSQLite(config.sqlite_path)
    sqlite.inicializar()

    if busca is None:
        repositorio_chunks = repositorio_chunks or RepositorioChunksChroma(
            config.chroma_path
        )
        busca_hibrida = BuscaHibrida(sqlite, repositorio_chunks)
    else:
        busca_hibrida = busca

    cliente_tjsp = TJSPClient(intervalo=config.intervalo_tjsp)
    if servico_tjsp is None:
        repositorio_chunks = repositorio_chunks or RepositorioChunksChroma(
            config.chroma_path
        )
        servico_coleta = ServicoColetaTJSP(
            sqlite,
            cliente_tjsp,
            PDFDownloader(
                cliente_tjsp,
                diretorio=config.diretorio_pdfs,
                limite_bytes=config.max_mb_pdf * 1024 * 1024,
            ),
            ProcessadorPDF(habilitar_ocr=config.habilitar_ocr),
            RepositorioChroma(config.chroma_path),
            repositorio_chunks,
            max_paginas=config.max_paginas_tjsp,
            max_pdfs=config.max_importacao_pdfs,
        )
    else:
        servico_coleta = servico_tjsp

    criar_provedor = provedor_factory or _criar_provedor_maritaca
    pesquisa_com_ia = pesquisa_assistida or PesquisaAssistidaTJSP(
        sqlite,
        servico_coleta,
        criar_provedor,
    )
    analise_de_documentos = analise_documental or AnaliseDocumentalTJSP(
        sqlite,
        busca_hibrida,
        criar_provedor,
    )
    preparador = PreparadorContextoIA(busca_hibrida)
    precos = PrecosTokens()

    app = FastAPI(
        title="TJSP Jurisprudência API",
        version="0.1.0",
        description="API para pesquisa jurisprudencial no TJSP e RAG jurídico com Maritaca AI.",
    )
    app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")

    @app.get("/", include_in_schema=False)
    def inicio() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/saude", tags=["sistema"])
    def saude() -> dict:
        contagens = sqlite.contagens_processamento()
        tesseract_disponivel = bool(shutil.which("tesseract"))

        sqlite_ok = True
        try:
            with sqlite._conectar() as conn:
                modo_journal = str(
                    conn.execute("PRAGMA journal_mode").fetchone()[0]
                ).lower()
        except Exception:
            sqlite_ok = False
            modo_journal = "indisponivel"

        chroma_ok = True
        total_chunks = 0
        if repositorio_chunks is not None:
            try:
                total_chunks = repositorio_chunks.colecao.count()
            except Exception:
                chroma_ok = False

        chave_maritaca = bool(os.environ.get("MARITACA_API_KEY", "").strip())
        status_geral = "ok" if (sqlite_ok and chroma_ok) else "atencao"

        return {
            "status": status_geral,
            "provedor_ia": "maritaca",
            "max_custo_brl": config.max_custo_brl,
            "max_output_tokens": config.max_output_tokens,
            "chunks_indexados": contagens["chunks_documento"],
            "max_paginas_tjsp": config.max_paginas_tjsp,
            "max_importacao_pdfs": config.max_importacao_pdfs,
            "intervalo_tjsp_segundos": config.intervalo_tjsp,
            "max_custo_pesquisa_assistida_brl": (
                config.max_custo_pesquisa_assistida_brl
            ),
            "max_custo_analise_documental_brl": (
                config.max_custo_analise_documental_brl
            ),
            "diagnosticos": {
                "sqlite": {
                    "status": "ok" if sqlite_ok else "erro",
                    "caminho": str(config.sqlite_path),
                    "journal_mode": modo_journal,
                    "contagens": contagens,
                },
                "chroma": {
                    "status": "ok" if chroma_ok else "erro",
                    "caminho": str(config.chroma_path),
                    "total_chunks": total_chunks,
                },
                "maritaca": {
                    "configurada": chave_maritaca,
                    "modelo": os.environ.get("MARITACA_MODEL", "sabia-4"),
                },
                "tesseract_ocr": {
                    "disponivel": tesseract_disponivel,
                    "habilitado": config.habilitar_ocr,
                },
            },
        }

    # Registro dos roteadores modulares
    app.include_router(
        criar_router_juris(
            sqlite=sqlite,
            busca_hibrida=busca_hibrida,
            servico_coleta=servico_coleta,
            cliente_tjsp=cliente_tjsp,
            config=config,
        )
    )
    app.include_router(
        criar_router_ia(
            sqlite=sqlite,
            pesquisa_com_ia=pesquisa_com_ia,
            analise_de_documentos=analise_de_documentos,
            preparador=preparador,
            precos=precos,
            criar_provedor=criar_provedor,
            config=config,
        )
    )

    return app
