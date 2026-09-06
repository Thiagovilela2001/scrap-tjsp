from __future__ import annotations

import random
import re
import threading
import time
from typing import ClassVar
from urllib.parse import urljoin, urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .adapters import DataJudAdapter, ESAJCJSGAdapter, STFAdapter, TJPRAdapter
from .captcha import BaseCaptchaSolver, obter_captcha_solver
from .models import Consulta, ResultadoPesquisa


class TokenBucket:
    """Limitador de taxa thread-safe baseado em Token Bucket com jitter.

    Garante espaçamento suave entre requisições respeitando o intervalo mínimo,
    com jitter aleatório para evitar padrões previsíveis de tráfego.
    """

    def __init__(
        self,
        intervalo: float = 2.0,
        *,
        capacidade: float = 1.0,
        jitter_max: float = 0.20,
    ) -> None:
        if intervalo < 1.0:
            raise ValueError("Intervalo mínimo permitido é 1 segundo.")
        self.intervalo = float(intervalo)
        self.taxa = 1.0 / self.intervalo
        self.capacidade = float(capacidade)
        self.tokens = float(capacidade)
        self.jitter_max = max(0.0, float(jitter_max))
        self.ultimo = time.monotonic()
        self._lock = threading.Lock()

    def aguardar(self, tokens: float = 1.0) -> None:
        with self._lock:
            agora = time.monotonic()
            decorrido = agora - self.ultimo
            self.ultimo = agora
            self.tokens = min(self.capacidade, self.tokens + decorrido * self.taxa)

            if self.tokens < tokens:
                necessario = tokens - self.tokens
                espera = necessario / self.taxa
                if self.jitter_max > 0:
                    espera += random.uniform(0, self.jitter_max)
                time.sleep(espera)
                self.ultimo = time.monotonic()
                self.tokens = 0.0
            else:
                self.tokens -= tokens

    def registrar(self) -> None:
        with self._lock:
            self.ultimo = time.monotonic()


TRIBUNAIS_CONFIG: dict[str, dict[str, str | bool]] = {
    # Adaptadores nativos e-SAJ/CJSG ativos
    "tjsp": {
        "sigla": "TJSP",
        "nome": "Tribunal de Justiça de São Paulo",
        "base_url": "https://esaj.tjsp.jus.br/cjsg/",
        "uf": "SP",
        "adaptador": "esaj_cjsg",
        "ativo": True,
    },
    "tjms": {
        "sigla": "TJMS",
        "nome": "Tribunal de Justiça de Mato Grosso do Sul",
        "base_url": "https://esaj.tjms.jus.br/cjsg/",
        "uf": "MS",
        "adaptador": "esaj_cjsg",
        "ativo": True,
    },
    "tjam": {
        "sigla": "TJAM",
        "nome": "Tribunal de Justiça do Amazonas",
        "base_url": "https://consultasaj.tjam.jus.br/cjsg/",
        "uf": "AM",
        "adaptador": "esaj_cjsg",
        "ativo": True,
    },
    "tjac": {
        "sigla": "TJAC",
        "nome": "Tribunal de Justiça do Acre",
        "base_url": "https://esaj.tjac.jus.br/cjsg/",
        "uf": "AC",
        "adaptador": "esaj_cjsg",
        "ativo": True,
    },
    # Adaptador nativo TJPR
    "tjpr": {
        "sigla": "TJPR",
        "nome": "Tribunal de Justiça do Paraná",
        "base_url": "https://portal.tjpr.jus.br/jurisprudencia/",
        "uf": "PR",
        "adaptador": "tjpr",
        "ativo": True,
    },
    # Tribunais de Justiça Estaduais integrados via DataJud (CNJ / Elasticsearch)
    "tjrj": {
        "sigla": "TJRJ",
        "nome": "Tribunal de Justiça do Rio de Janeiro",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "RJ",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tjmg": {
        "sigla": "TJMG",
        "nome": "Tribunal de Justiça de Minas Gerais",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "MG",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tjes": {
        "sigla": "TJES",
        "nome": "Tribunal de Justiça do Espírito Santo",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "ES",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tjrs": {
        "sigla": "TJRS",
        "nome": "Tribunal de Justiça do Rio Grande do Sul",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "RS",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tjsc": {
        "sigla": "TJSC",
        "nome": "Tribunal de Justiça de Santa Catarina",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "SC",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tjdft": {
        "sigla": "TJDFT",
        "nome": "Tribunal de Justiça do Distrito Federal e dos Territórios",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "DF",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tjgo": {
        "sigla": "TJGO",
        "nome": "Tribunal de Justiça de Goiás",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "GO",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tjmt": {
        "sigla": "TJMT",
        "nome": "Tribunal de Justiça de Mato Grosso",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "MT",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tjba": {
        "sigla": "TJBA",
        "nome": "Tribunal de Justiça da Bahia",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "BA",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tjpe": {
        "sigla": "TJPE",
        "nome": "Tribunal de Justiça de Pernambuco",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "PE",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tjce": {
        "sigla": "TJCE",
        "nome": "Tribunal de Justiça do Ceará",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "CE",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tjma": {
        "sigla": "TJMA",
        "nome": "Tribunal de Justiça do Maranhão",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "MA",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tjpb": {
        "sigla": "TJPB",
        "nome": "Tribunal de Justiça da Paraíba",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "PB",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tjrn": {
        "sigla": "TJRN",
        "nome": "Tribunal de Justiça do Rio Grande do Norte",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "RN",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tjal": {
        "sigla": "TJAL",
        "nome": "Tribunal de Justiça de Alagoas",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "AL",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tjpi": {
        "sigla": "TJPI",
        "nome": "Tribunal de Justiça do Piauí",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "PI",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tjse": {
        "sigla": "TJSE",
        "nome": "Tribunal de Justiça de Sergipe",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "SE",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tjpa": {
        "sigla": "TJPA",
        "nome": "Tribunal de Justiça do Pará",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "PA",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tjro": {
        "sigla": "TJRO",
        "nome": "Tribunal de Justiça de Rondônia",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "RO",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tjto": {
        "sigla": "TJTO",
        "nome": "Tribunal de Justiça do Tocantins",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "TO",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tjap": {
        "sigla": "TJAP",
        "nome": "Tribunal de Justiça do Amapá",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "AP",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tjrr": {
        "sigla": "TJRR",
        "nome": "Tribunal de Justiça de Roraima",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "RR",
        "adaptador": "datajud",
        "ativo": True,
    },
    # Tribunais Regionais Federais (DataJud / CNJ)
    "trf1": {
        "sigla": "TRF1",
        "nome": "Tribunal Regional Federal da 1ª Região",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "DF",
        "adaptador": "datajud",
        "ativo": True,
    },
    "trf2": {
        "sigla": "TRF2",
        "nome": "Tribunal Regional Federal da 2ª Região",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "RJ",
        "adaptador": "datajud",
        "ativo": True,
    },
    "trf3": {
        "sigla": "TRF3",
        "nome": "Tribunal Regional Federal da 3ª Região",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "SP",
        "adaptador": "datajud",
        "ativo": True,
    },
    "trf4": {
        "sigla": "TRF4",
        "nome": "Tribunal Regional Federal da 4ª Região",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "RS",
        "adaptador": "datajud",
        "ativo": True,
    },
    "trf5": {
        "sigla": "TRF5",
        "nome": "Tribunal Regional Federal da 5ª Região",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "PE",
        "adaptador": "datajud",
        "ativo": True,
    },
    "trf6": {
        "sigla": "TRF6",
        "nome": "Tribunal Regional Federal da 6ª Região",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "MG",
        "adaptador": "datajud",
        "ativo": True,
    },
    # Tribunais Superiores
    "stj": {
        "sigla": "STJ",
        "nome": "Superior Tribunal de Justiça",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "DF",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tst": {
        "sigla": "TST",
        "nome": "Tribunal Superior do Trabalho",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "DF",
        "adaptador": "datajud",
        "ativo": True,
    },
    "tse": {
        "sigla": "TSE",
        "nome": "Tribunal Superior Eleitoral",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "DF",
        "adaptador": "datajud",
        "ativo": True,
    },
    "stm": {
        "sigla": "STM",
        "nome": "Superior Tribunal Militar",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": "DF",
        "adaptador": "datajud",
        "ativo": True,
    },
    "stf": {
        "sigla": "STF",
        "nome": "Supremo Tribunal Federal",
        "base_url": "https://jurisprudencia.stf.jus.br",
        "uf": "DF",
        "adaptador": "stf",
        "ativo": True,
    },
}

# Alias
TRIBUNAIS_CONFIG["tjdf"] = TRIBUNAIS_CONFIG["tjdft"]

TRIBUNAIS_DATAJUD: dict[str, tuple[str, str]] = {
    # Sudeste
    "datajud_tjsp": ("TJSP", "SP"),
    "datajud_tjrj": ("TJRJ", "RJ"),
    "datajud_tjmg": ("TJMG", "MG"),
    "datajud_tjes": ("TJES", "ES"),
    # Sul
    "datajud_tjrs": ("TJRS", "RS"),
    "datajud_tjpr": ("TJPR", "PR"),
    "datajud_tjsc": ("TJSC", "SC"),
    # Centro-Oeste
    "datajud_tjdft": ("TJDFT", "DF"),
    "datajud_tjdf": ("TJDFT", "DF"),
    "datajud_tjgo": ("TJGO", "GO"),
    "datajud_tjmt": ("TJMT", "MT"),
    "datajud_tjms": ("TJMS", "MS"),
    # Nordeste
    "datajud_tjba": ("TJBA", "BA"),
    "datajud_tjpe": ("TJPE", "PE"),
    "datajud_tjce": ("TJCE", "CE"),
    "datajud_tjma": ("TJMA", "MA"),
    "datajud_tjpb": ("TJPB", "PB"),
    "datajud_tjrn": ("TJRN", "RN"),
    "datajud_tjal": ("TJAL", "AL"),
    "datajud_tjpi": ("TJPI", "PI"),
    "datajud_tjse": ("TJSE", "SE"),
    # Norte
    "datajud_tjpa": ("TJPA", "PA"),
    "datajud_tjam": ("TJAM", "AM"),
    "datajud_tjro": ("TJRO", "RO"),
    "datajud_tjto": ("TJTO", "TO"),
    "datajud_tjac": ("TJAC", "AC"),
    "datajud_tjap": ("TJAP", "AP"),
    "datajud_tjrr": ("TJRR", "RR"),
    # Tribunais Regionais Federais
    "datajud_trf1": ("TRF1", "DF"),
    "datajud_trf2": ("TRF2", "RJ"),
    "datajud_trf3": ("TRF3", "SP"),
    "datajud_trf4": ("TRF4", "RS"),
    "datajud_trf5": ("TRF5", "PE"),
    "datajud_trf6": ("TRF6", "MG"),
    # Tribunais Superiores
    "datajud_stj": ("STJ", "DF"),
    "datajud_tst": ("TST", "DF"),
    "datajud_tse": ("TSE", "DF"),
    "datajud_stm": ("STM", "DF"),
}

for _cod, (_sigla, _uf) in TRIBUNAIS_DATAJUD.items():
    TRIBUNAIS_CONFIG[_cod] = {
        "sigla": _sigla,
        "nome": f"Tribunal {_sigla} (DataJud / CNJ)",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": _uf,
        "adaptador": "datajud",
        "ativo": True,
    }


def tribunais_ativos(*, adaptador: str | None = None) -> tuple[str, ...]:
    return tuple(
        codigo
        for codigo, config in TRIBUNAIS_CONFIG.items()
        if config.get("ativo") is True
        and (adaptador is None or config.get("adaptador") == adaptador)
    )


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
            sigla_datajud = (
                self.tribunal.replace("datajud_", "").replace("_datajud", "")
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
            return TJPRAdapter(
                "https://portal.tjpr.jus.br/jurisprudencia/"
            ).obter_pdf(self._requisicao_url, url)
        if (
            destino.scheme == "https"
            and destino.hostname == "api-publica.datajud.cnj.jus.br"
        ):
            from .settings import get_settings

            st = get_settings()
            sigla_datajud = self.tribunal.replace("datajud_", "").replace("_datajud", "")
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
        try:
            resposta = self.session.request(
                metodo,
                url,
                timeout=self.timeout,
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
