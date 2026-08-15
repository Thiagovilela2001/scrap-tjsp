"""Coletor responsável de jurisprudência pública do TJSP."""

from .assisted_research import (
    ConfiguracaoPesquisaAssistida,
    ErroPesquisaAssistida,
    LimiteCustoPesquisa,
    PesquisaAssistidaTJSP,
)
from .client import TJSPClient
from .document_analysis import (
    AnaliseDocumentalTJSP,
    ConfiguracaoAnaliseDocumental,
    ErroAnaliseDocumental,
    LimiteCustoAnalise,
    RecuperadorDocumentosJuridicos,
)
from .downloader import DownloadPDFError, PDFDownloader
from .evaluation import AvaliadorJuridico, CasoAvaliacao, JuizJuridicoIA
from .ingestion import ServicoColetaTJSP
from .legal_validation import validar_resposta_juridica
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
from .rag import PacoteContextoIA, PreparadorContextoIA, ProvedorIA, RespostaIA
from .search import BuscaHibrida, ResultadoBuscaHibrida
from .storage import RepositorioSQLite
from .vector_store import RepositorioChroma, RepositorioChunksChroma

__all__ = [
    "AnaliseDocumentalTJSP",
    "AvaliadorJuridico",
    "BuscaHibrida",
    "CasoAvaliacao",
    "ChunkJuridico",
    "ConfiguracaoAnaliseDocumental",
    "ConfiguracaoPesquisaAssistida",
    "Consulta",
    "Decisao",
    "DocumentoBaixado",
    "DownloadPDFError",
    "ErroAnaliseDocumental",
    "ErroMaritaca",
    "ErroPesquisaAssistida",
    "JuizJuridicoIA",
    "LimiteCustoAnalise",
    "LimiteCustoPesquisa",
    "PDFDownloader",
    "PacoteContextoIA",
    "PaginaExtraida",
    "PesquisaAssistidaTJSP",
    "PreparadorContextoIA",
    "ProcessadorPDF",
    "ProcessamentoPDFError",
    "ProvedorIA",
    "ProvedorMaritaca",
    "RecuperadorDocumentosJuridicos",
    "RepositorioChroma",
    "RepositorioChunksChroma",
    "RepositorioSQLite",
    "RespostaIA",
    "ResultadoBuscaHibrida",
    "ResultadoPesquisa",
    "ResultadoProcessamento",
    "ServicoColetaTJSP",
    "TJSPClient",
    "validar_resposta_juridica",
]
