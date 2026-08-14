"""Coletor responsável de jurisprudência pública do TJSP."""

from .client import TJSPClient
from .downloader import DownloadPDFError, PDFDownloader
from .maritaca import ErroMaritaca, ProvedorMaritaca
from .models import (
    ChunkJuridico,
    Consulta,
    Decisao,
    DocumentoBaixado,
    PaginaExtraida,
    ResultadoPesquisa,
    ResultadoProcessamento,
)
from .processor import ProcessadorPDF, ProcessamentoPDFError
from .rag import PacoteContextoIA, PreparadorContextoIA, ProvedorIA
from .search import BuscaHibrida, ResultadoBuscaHibrida
from .storage import RepositorioSQLite
from .vector_store import RepositorioChroma, RepositorioChunksChroma

__all__ = [
    "BuscaHibrida",
    "ChunkJuridico",
    "Consulta",
    "Decisao",
    "DocumentoBaixado",
    "DownloadPDFError",
    "ErroMaritaca",
    "PDFDownloader",
    "PacoteContextoIA",
    "PaginaExtraida",
    "PreparadorContextoIA",
    "ProcessadorPDF",
    "ProcessamentoPDFError",
    "ProvedorIA",
    "ProvedorMaritaca",
    "RepositorioChroma",
    "RepositorioChunksChroma",
    "RepositorioSQLite",
    "ResultadoBuscaHibrida",
    "ResultadoPesquisa",
    "ResultadoProcessamento",
    "TJSPClient",
]
