from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

import requests

from ..models import Consulta, Decisao, ResultadoPesquisa


@dataclass(frozen=True, slots=True)
class DataJudAdapter:
    """Adaptador oficial para a API Pública do DataJud (CNJ) via Elasticsearch."""

    base_url: str = "https://api-publica.datajud.cnj.jus.br"
    api_key: str = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
    sigla_tribunal: str = "tjce"

    TAMANHO_PAGINA: ClassVar[int] = 20

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

    @property
    def indice_tribunal(self) -> str:
        sigla = self.sigla_tribunal.lower().strip()
        if sigla == "tjdf":
            sigla = "tjdft"
        if not sigla.startswith("api_publica_"):
            return f"api_publica_{sigla}"
        return sigla

    def url(self, caminho: str = "_search") -> str:
        return f"{self.base_url}/{self.indice_tribunal}/{caminho.lstrip('/')}"

    def montar_query_elasticsearch(
        self, consulta: Consulta, *, pagina: int = 1, tamanho: int = 20
    ) -> dict[str, Any]:
        """Gera payload DSL do Elasticsearch a partir da Consulta."""
        must_clauses: list[dict[str, Any]] = []

        termo = consulta.pesquisa.strip() or consulta.ementa.strip()
        if termo:
            must_clauses.append(
                {
                    "multi_match": {
                        "query": termo,
                        "fields": [
                            "classe.nome^2",
                            "assuntos.nome^2",
                            "orgaoJulgador.nome",
                            "movimentos.nome",
                            "numeroProcesso",
                        ],
                    }
                }
            )

        if consulta.classe.strip():
            must_clauses.append({"match": {"classe.nome": consulta.classe.strip()}})

        if consulta.assunto.strip():
            must_clauses.append({"match": {"assuntos.nome": consulta.assunto.strip()}})

        if consulta.orgao_julgador.strip():
            must_clauses.append(
                {"match": {"orgaoJulgador.nome": consulta.orgao_julgador.strip()}}
            )

        query_body: dict[str, Any] = {
            "from": (pagina - 1) * tamanho,
            "size": tamanho,
            "query": {"bool": {"must": must_clauses}}
            if must_clauses
            else {"match_all": {}},
            "sort": [
                {"dataAjuizamento": {"order": "desc", "unmapped_type": "keyword"}}
            ],
        }
        return query_body

    def pesquisar(
        self,
        requisitar: Callable[..., requests.Response],
        consulta: Consulta,
        *,
        max_paginas: int = 1,
    ) -> ResultadoPesquisa:
        decisoes: list[Decisao] = []
        total = 0
        paginas_coletadas = 0

        headers = {
            "Authorization": f"APIKey {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        for pagina in range(1, max_paginas + 1):
            payload = self.montar_query_elasticsearch(
                consulta,
                pagina=pagina,
                tamanho=self.TAMANHO_PAGINA,
            )
            resposta = requisitar(
                "POST",
                self.url("_search"),
                json=payload,
                headers=headers,
            )
            resposta.raise_for_status()
            dados = resposta.json()

            total_hits = dados.get("hits", {}).get("total", {})
            if isinstance(total_hits, dict):
                total = int(total_hits.get("value", 0))
            else:
                total = int(total_hits)

            hits = dados.get("hits", {}).get("hits", [])
            if not hits:
                break

            for hit in hits:
                decisao = self._parsear_hit(hit)
                if decisao is not None:
                    decisoes.append(decisao)

            paginas_coletadas += 1
            if len(decisoes) >= total or len(hits) < self.TAMANHO_PAGINA:
                break

        return ResultadoPesquisa(
            total_disponivel=total,
            paginas_coletadas=paginas_coletadas,
            decisoes=tuple(decisoes),
        )

    def _parsear_hit(self, hit: dict[str, Any]) -> Decisao | None:
        source: dict[str, Any] = hit.get("_source", {})
        if not source:
            return None

        numero_processo = str(source.get("numeroProcesso", "")).strip()
        doc_id = str(hit.get("_id", "") or source.get("id", "")).strip()
        cd_acordao = "".join(c for c in (doc_id or numero_processo) if c.isdigit())
        if not cd_acordao:
            cd_acordao = "1000000000"

        classe = str(source.get("classe", {}).get("nome", "Decisão")).strip()
        assuntos_lista = [
            str(a.get("nome", "")).strip()
            for a in source.get("assuntos", [])
            if a.get("nome")
        ]
        assunto = "; ".join(assuntos_lista)
        orgao = str(source.get("orgaoJulgador", {}).get("nome", "")).strip()

        # Extrai movimentos / ementa / histórico
        movimentos = source.get("movimentos", [])
        movimentos_nomes = [
            str(m.get("nome", "")).strip() for m in movimentos if m.get("nome")
        ]
        ementa = (
            f"Movimentações DataJud: {', '.join(movimentos_nomes[:5])}"
            if movimentos_nomes
            else "Dados processuais DataJud."
        )

        data_raw = (
            source.get("dataAjuizamento")
            or source.get("dataHoraUltimaAtualizacao")
            or ""
        )
        data_formatada = self._formatar_data(data_raw)

        inteiro_teor = (
            f"{self.base_url}/{self.indice_tribunal}/_doc/{hit.get('_id', '')}"
        )

        return Decisao(
            processo=numero_processo or doc_id,
            cd_acordao=cd_acordao,
            cd_foro="0",
            classe=classe,
            assunto=assunto,
            relator="",
            comarca="",
            orgao_julgador=orgao,
            data_julgamento=data_formatada,
            data_publicacao=data_formatada,
            ementa=ementa,
            inteiro_teor_url=inteiro_teor,
        )

    @staticmethod
    def _formatar_data(valor: str) -> str:
        """Converte formatos como YYYYMMDDHHMMSS ou YYYY-MM-DD em DD/MM/YYYY."""
        limpo = valor.strip()
        if not limpo:
            return ""
        if len(limpo) >= 8 and limpo[:8].isdigit():
            ano = limpo[:4]
            mes = limpo[4:6]
            dia = limpo[6:8]
            return f"{dia}/{mes}/{ano}"
        match = re.search(r"(\d{4})-(\d{2})-(\d{2})", limpo)
        if match:
            return f"{match.group(3)}/{match.group(2)}/{match.group(1)}"
        return limpo

    def obter_pdf(
        self,
        requisitar: Callable[..., requests.Response],
        url_doc: str,
    ) -> requests.Response:
        from urllib.parse import urlsplit

        destino = urlsplit(url_doc)
        if (
            destino.scheme != "https"
            or not destino.hostname
            or "datajud.cnj.jus.br" not in destino.hostname
        ):
            raise ValueError("URL de inteiro teor fora da API pública do DataJud.")

        headers = {
            "Authorization": f"APIKey {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = requisitar("GET", url_doc, headers=headers)
        dados = resp.json()
        source = dados.get("_source", {})
        conteudo_pdf = self._gerar_pdf_processo(source)

        resposta = requests.Response()
        resposta.status_code = 200
        resposta.url = url_doc
        resposta.headers["Content-Type"] = "application/pdf"
        resposta.headers["Content-Length"] = str(len(conteudo_pdf))
        resposta._content = conteudo_pdf
        resposta._content_consumed = True
        return resposta

    def _gerar_pdf_processo(self, source: dict[str, Any]) -> bytes:
        from .datajud_pdf import gerar_pdf_processo

        return gerar_pdf_processo(source, self.sigla_tribunal, self._formatar_data)
