from __future__ import annotations

import re
from typing import ClassVar
from urllib.parse import urljoin, urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .adapters import DataJudAdapter, ESAJCJSGAdapter, STFAdapter, TJPRAdapter
from .captcha import BaseCaptchaSolver, obter_captcha_solver
from .models import Consulta, ResultadoPesquisa
from .rate_limiter import TokenBucket
from .tribunais_config import TRIBUNAIS_CONFIG, TRIBUNAIS_DATAJUD, tribunais_ativos

__all__ = [
    "TRIBUNAIS_CONFIG",
    "TRIBUNAIS_DATAJUD",
    "TJSPClient",
    "TokenBucket",
    "tribunais_ativos",
]


class TJSPClient:
    BASE_URL = "https://esaj.tjsp.jus.br/cjsg/"
    TIPOS: ClassVar[dict[str, str]] = ESAJCJSGAdapter.TIPOS
    ORIGENS: ClassVar[dict[str, str]] = ESAJCJSGAdapter.ORIGENS

    def __init__(
        self,
        *,
        tribunal: str = "tjsp",
        base_url: str | None = None,
        intervalo: float = 2.0,
        timeout: float = 30.0,
        session: requests.Session | None = None,
        limitador: TokenBucket | None = None,
        captcha_solver: BaseCaptchaSolver | None = None,
    ) -> None:
        if intervalo < 1.0:
            raise ValueError("Intervalo mínimo permitido é 1 segundo.")
        self.tribunal = tribunal.lower().strip()
        config_trib = TRIBUNAIS_CONFIG.get(self.tribunal, {})
        if not config_trib and self.tribunal.startswith("datajud_"):
            sigla_trib = self.tribunal.removeprefix("datajud_")
            config_trib = {
                "sigla": sigla_trib.upper(),
                "nome": f"Tribunal {sigla_trib.upper()} (DataJud / CNJ)",
                "base_url": "https://api-publica.datajud.cnj.jus.br",
                "uf": "BR",
                "adaptador": "datajud",
                "ativo": True,
            }
        if not config_trib and base_url is None:
            raise ValueError(f"Tribunal não configurado: {self.tribunal.upper()}.")
        if config_trib and config_trib.get("ativo") is not True and base_url is None:
            motivo = config_trib.get("motivo_inativo", "adaptador indisponível")
            raise ValueError(f"{self.tribunal.upper()} inativo: {motivo}")
        self.sigla = str(config_trib.get("sigla", self.tribunal.upper()))
        self.base_url = str(base_url or config_trib.get("base_url", self.BASE_URL))
        adaptador = config_trib.get("adaptador", "esaj_cjsg")
        if adaptador == "esaj_cjsg":
            self.adapter = ESAJCJSGAdapter(self.base_url)
        elif adaptador == "tjpr":
            self.adapter = TJPRAdapter(self.base_url)
        elif adaptador == "datajud":
            from .settings import get_settings

            st = get_settings()
            sigla_datajud = self.tribunal.replace("datajud_", "").replace(
                "_datajud", ""
            )
            self.adapter = DataJudAdapter(
                base_url=self.base_url,
                api_key=st.datajud_api_key,
                sigla_tribunal=sigla_datajud,
            )
        elif adaptador == "stf":
            self.adapter = STFAdapter(self.base_url)
        else:
            raise ValueError(f"Adaptador não suportado: {adaptador}.")
        self.base_url = self.adapter.base_url
        self.timeout = timeout
        self.session = session or requests.Session()
        self._limitador = limitador or TokenBucket(intervalo)
        self.captcha_solver = captcha_solver or obter_captcha_solver()
        self._configurar_session()

    def pesquisar(
        self, consulta: Consulta, *, max_paginas: int = 1
    ) -> ResultadoPesquisa:
        consulta.validar()
        if max_paginas < 1:
            raise ValueError("max_paginas deve ser pelo menos 1.")

        return self.adapter.pesquisar(
            self._requisicao_url,
            consulta,
            max_paginas=max_paginas,
        )

    def _configurar_session(self) -> None:
        self.session.headers.update(
            {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/143.0.0.0 Safari/537.36"
                ),
            }
        )
        retentativas = Retry(
            total=4,
            connect=3,
            read=3,
            status=3,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(
            max_retries=retentativas,
            pool_connections=10,
            pool_maxsize=20,
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _requisicao(self, metodo: str, caminho: str, **kwargs) -> requests.Response:
        return self._requisicao_url(metodo, f"{self.base_url}{caminho}", **kwargs)

    def obter_pdf(self, url: str) -> requests.Response:
        destino = urlsplit(url)
        if (
            destino.scheme == "https"
            and destino.hostname == "portal.tjpr.jus.br"
            and destino.path.startswith("/jurisprudencia/j/")
        ):
            return TJPRAdapter("https://portal.tjpr.jus.br/jurisprudencia/").obter_pdf(
                self._requisicao_url, url
            )
        if (
            destino.scheme == "https"
            and destino.hostname == "api-publica.datajud.cnj.jus.br"
        ):
            from .settings import get_settings

            st = get_settings()
            sigla_datajud = self.tribunal.replace("datajud_", "").replace(
                "_datajud", ""
            )
            return DataJudAdapter(
                base_url="https://api-publica.datajud.cnj.jus.br",
                api_key=st.datajud_api_key,
                sigla_tribunal=sigla_datajud,
            ).obter_pdf(self._requisicao_url, url)
        if (
            destino.scheme != "https"
            or not (destino.hostname and "jus.br" in destino.hostname)
            or not destino.path.endswith("getArquivo.do")
        ):
            raise ValueError(
                f"URL de PDF fora do endpoint público permitido do tribunal ({url})."
            )

        resposta = self._requisicao_url(
            "GET",
            url,
            stream=True,
            headers={"Accept": "application/pdf,text/html"},
        )

        content_type = resposta.headers.get("Content-Type", "").lower()
        if "application/pdf" in content_type:
            return resposta

        # Verifica se o endpoint retornou página HTML de captcha
        corpo = resposta.content
        if (
            b"g-recaptcha" in corpo
            or b"uuidCaptcha" in corpo
            or b"captcha" in corpo.lower()
        ):
            resposta_resolvida = self._tentar_resolver_captcha_pdf(url, corpo)
            if resposta_resolvida is not None:
                return resposta_resolvida

        # Devolve resposta original encapsulando o conteúdo já lido
        resp_final = requests.Response()
        resp_final.status_code = resposta.status_code
        resp_final.url = resposta.url
        resp_final.headers.update(resposta.headers)
        resp_final._content = corpo
        resp_final._content_consumed = True
        return resp_final

    def _tentar_resolver_captcha_pdf(
        self, url: str, corpo_html: bytes
    ) -> requests.Response | None:
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(corpo_html, "html.parser")
            form = soup.find("form")
            if not form:
                return None

            dados_post: dict[str, str] = {}
            for inp in form.find_all("input"):
                nome = inp.get("name")
                if nome:
                    dados_post[nome] = inp.get("value", "")

            # Caso 1: reCAPTCHA do Google
            recaptcha_el = soup.find(class_=re.compile(r"g-recaptcha"))
            if recaptcha_el and recaptcha_el.get("data-sitekey"):
                sitekey = str(recaptcha_el["data-sitekey"]).strip()
                token = self.captcha_solver.resolver_recaptcha(sitekey, url)
                dados_post["g-recaptcha-response"] = token
                if "uuidCaptcha" in dados_post and not dados_post["uuidCaptcha"]:
                    dados_post["uuidCaptcha"] = token

            # Caso 2: Desafio visual de imagem
            img_el = soup.find("img", src=re.compile(r"captcha|imagem", re.IGNORECASE))
            if img_el and img_el.get("src"):
                img_url = urljoin(url, str(img_el["src"]))
                img_resp = self._requisicao_url("GET", img_url)
                codigo = self.captcha_solver.resolver_imagem(img_resp.content)
                for campo in ("codigo", "codigoAcesso", "respostaCaptcha", "palavra"):
                    if campo in dados_post:
                        dados_post[campo] = codigo

            action_url = urljoin(url, str(form.get("action", url)))
            resposta_post = self._requisicao_url(
                "POST",
                action_url,
                data=dados_post,
                headers={"Referer": url, "Accept": "application/pdf"},
                stream=True,
            )
            content_type_post = resposta_post.headers.get("Content-Type", "").lower()
            if (
                "application/pdf" in content_type_post
                or resposta_post.content.startswith(b"%PDF-")
            ):
                return resposta_post
        except Exception:
            pass
        return None

    def _requisicao_url(self, metodo: str, url: str, **kwargs) -> requests.Response:
        self._limitador.aguardar()
        timeout = kwargs.pop("timeout", self.timeout)
        try:
            resposta = self.session.request(
                metodo,
                url,
                timeout=timeout,
                **kwargs,
            )
            resposta.raise_for_status()
            return resposta
        finally:
            self._limitador.registrar()

    def _corpo(self, consulta: Consulta) -> dict[str, str]:
        if not isinstance(self.adapter, ESAJCJSGAdapter):
            raise ValueError("Corpo e-SAJ indisponível para este adaptador.")
        return self.adapter.corpo_consulta(consulta)
