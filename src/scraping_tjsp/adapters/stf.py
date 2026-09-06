from __future__ import annotations

import logging
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..models import Consulta, Decisao, ResultadoPesquisa

logger = logging.getLogger(__name__)


def _formatar_data_stf(data_str: str | None) -> str:
    if not data_str:
        return ""
    data_limpa = str(data_str).strip()
    if "-" in data_limpa:
        try:
            return datetime.strptime(data_limpa[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            pass
    return data_limpa


def converter_hit_stf(source: dict[str, Any]) -> Decisao:
    """Converte um documento _source retornado pelo Elasticsearch do STF em um modelo Decisao."""
    relator_lista = source.get("ministro_facet")
    if isinstance(relator_lista, list) and relator_lista:
        relator = ", ".join(str(m) for m in relator_lista)
    else:
        relator = str(source.get("relator_processo_nome") or "")

    processo = (
        str(source.get("processo_codigo_completo") or "")
        or str(source.get("titulo") or "")
        or str(source.get("id") or "")
    )

    cd_acordao = str(source.get("id") or source.get("processo_numero") or processo)

    classe = (
        str(source.get("processo_classe_processual_unificada_classe_sigla") or "")
        or str(source.get("processo_classe_processual_unificada_extenso") or "")
        or "Acórdão STF"
    )

    assunto = (
        str(source.get("documental_assunto_texto") or "")
        or str(source.get("ramo_direito") or "")
        or "Direito Constitucional"
    )

    comarca = str(source.get("procedencia_geografica_completo") or "Brasília/DF")
    orgao_julgador = str(source.get("orgao_julgador") or "Supremo Tribunal Federal")
    data_julgamento = _formatar_data_stf(source.get("julgamento_data"))
    data_publicacao = _formatar_data_stf(source.get("publicacao_data"))
    ementa = str(source.get("ementa_texto") or "").strip()
    inteiro_teor_url = str(source.get("inteiro_teor_url") or "")

    return Decisao(
        processo=processo,
        cd_acordao=cd_acordao,
        cd_foro="0",
        classe=classe,
        assunto=assunto,
        relator=relator,
        comarca=comarca,
        orgao_julgador=orgao_julgador,
        data_julgamento=data_julgamento,
        data_publicacao=data_publicacao,
        ementa=ementa,
        inteiro_teor_url=inteiro_teor_url,
    )


@dataclass(frozen=True, slots=True)
class STFAdapter:
    """Adaptador para consulta de jurisprudência do Supremo Tribunal Federal (STF)."""

    base_url: str = "https://jurisprudencia.stf.jus.br"
    timeout_ms: int = 35000

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

    def url(self, caminho: str = "pages/search") -> str:
        return f"{self.base_url}/{caminho.lstrip('/')}"

    def pesquisar(
        self,
        requisicao_url: Callable[..., Any],
        consulta: Consulta,
        *,
        max_paginas: int = 1,
    ) -> ResultadoPesquisa:
        """Executa busca de acórdãos no STF utilizando Playwright stealth para resolver o AWS WAF."""
        from playwright.sync_api import sync_playwright

        termo = consulta.pesquisa.strip() or consulta.ementa.strip()
        if not termo:
            raise ValueError("Pesquisa ou ementa deve ser informada para o STF.")

        decisoes: list[Decisao] = []
        total_encontrado = 0
        paginas_coletadas = 0

        with sync_playwright() as p:
            browser = None
            for canal in ("chrome", "msedge", None):
                try:
                    kwargs: dict[str, Any] = {
                        "headless": True,
                        "args": [
                            "--disable-blink-features=AutomationControlled",
                            "--no-sandbox",
                            "--disable-dev-shm-usage",
                        ],
                    }
                    if canal:
                        kwargs["channel"] = canal
                    browser = p.chromium.launch(**kwargs)
                    break
                except Exception as exc:
                    logger.debug("Tentativa com canal %s falhou: %s", canal, exc)

            if not browser:
                raise RuntimeError(
                    "Não foi possível iniciar o navegador Chromium/Chrome/Edge para consulta ao STF."
                )

            try:
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 800},
                    ignore_https_errors=True,
                )
                page = context.new_page()
                page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                )

                for pagina in range(1, max_paginas + 1):
                    captured_data: list[dict[str, Any]] = []

                    def on_response(resp):
                        if "api/search" in resp.url and resp.status == 200:
                            try:
                                captured_data.append(resp.json())
                            except Exception:
                                pass

                    page.on("response", on_response)

                    query_enc = urllib.parse.quote(termo)
                    url_busca = (
                        f"{self.base_url}/pages/search"
                        f"?base=acordaos&queryString={query_enc}&page={pagina}"
                    )
                    page.goto(url_busca, wait_until="networkidle", timeout=self.timeout_ms)
                    page.remove_listener("response", on_response)

                    if not captured_data:
                        break

                    data = captured_data[0]
                    result = data.get("result", {})
                    hits = result.get("hits", {})
                    total_encontrado = hits.get("total", {}).get("value", total_encontrado)

                    documentos = hits.get("hits", [])
                    if not documentos:
                        break

                    for doc in documentos:
                        source = doc.get("_source", {})
                        decisoes.append(converter_hit_stf(source))

                    paginas_coletadas += 1

            finally:
                browser.close()

        return ResultadoPesquisa(
            total_disponivel=total_encontrado,
            paginas_coletadas=paginas_coletadas,
            decisoes=decisoes,
        )
