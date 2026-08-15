from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from .rag import FonteContexto

_CITACAO = re.compile(r"\[Fonte\s+(\d+)\]", re.IGNORECASE)
_PADROES = {
    "processo": re.compile(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b"),
    "acordao": re.compile(
        r"\bac[oó]rd[aã]o\s+(?:n[º°o.]?\s*)?(\d{4,})\b",
        re.IGNORECASE,
    ),
    "tema": re.compile(r"\btema\s+(?:n[º°o.]?\s*)?(\d{1,5})\b", re.IGNORECASE),
    "sumula": re.compile(
        r"\bs[uú]mula\s+(?:n[º°o.]?\s*)?(\d{1,5})\b",
        re.IGNORECASE,
    ),
    "artigo": re.compile(
        r"\bart(?:s?\.?|igos?)\s*(\d+[A-Za-z]?)\b",
        re.IGNORECASE,
    ),
    "pagina": re.compile(
        r"\b(?:p[aá]gina|p\.)\s*(\d{1,5})\b",
        re.IGNORECASE,
    ),
    "percentual": re.compile(r"(?<!\w)\d+(?:[.,]\d+)?\s*%"),
    "valor": re.compile(r"R\$\s*\d[\d.]*(?:,\d{2})?\b", re.IGNORECASE),
    "data": re.compile(r"\b\d{2}/\d{2}/\d{4}\b"),
}


def validar_resposta_juridica(
    resposta: str,
    fontes: Iterable[FonteContexto],
) -> dict:
    fontes = tuple(fontes)
    permitidas = {fonte.numero for fonte in fontes}
    citacoes = [int(numero) for numero in _CITACAO.findall(resposta)]
    citacoes_invalidas = sorted(set(citacoes) - permitidas)

    corpus = "\n".join(f"{fonte.citacao}\n{fonte.texto}" for fonte in fontes)
    referencias_fontes = _extrair_referencias(corpus)
    referencias_resposta = _extrair_referencias(resposta)
    verificacoes = []
    for tipo, valores in referencias_resposta.items():
        for valor in valores:
            verificacoes.append(
                {
                    "tipo": tipo,
                    "valor": valor,
                    "verificada": valor in referencias_fontes[tipo],
                }
            )
    nao_verificadas = [item for item in verificacoes if not item["verificada"]]
    return {
        "aprovada": bool(citacoes) and not citacoes_invalidas and not nao_verificadas,
        "fontes_citadas": sorted(set(citacoes) & permitidas),
        "citacoes_invalidas": citacoes_invalidas,
        "referencias": verificacoes,
        "referencias_nao_verificadas": nao_verificadas,
    }


def _extrair_referencias(texto: str) -> dict[str, set[str]]:
    referencias: dict[str, set[str]] = {}
    for tipo, padrao in _PADROES.items():
        valores = set()
        for ocorrencia in padrao.finditer(texto or ""):
            valor = ocorrencia.group(1) if ocorrencia.lastindex else ocorrencia.group(0)
            valores.add(_normalizar(tipo, valor))
        referencias[tipo] = valores
    return referencias


def _normalizar(tipo: str, valor: str) -> str:
    normalizado = unicodedata.normalize("NFKD", valor)
    normalizado = "".join(
        caractere for caractere in normalizado if not unicodedata.combining(caractere)
    )
    normalizado = re.sub(r"\s+", " ", normalizado).strip().casefold()
    if tipo == "valor":
        return normalizado.replace(".", "").replace(",", ".")
    if tipo == "percentual":
        return normalizado.replace(" ", "").replace(",", ".")
    return normalizado
