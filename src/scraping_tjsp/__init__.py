"""Coletor responsável de jurisprudência pública do TJSP."""

from .client import TJSPClient
from .models import Decisao, ResultadoPesquisa, Consulta

__all__ = ["Consulta", "Decisao", "ResultadoPesquisa", "TJSPClient"]
