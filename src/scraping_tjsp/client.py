from __future__ import annotations

import random
import threading
import time
from typing import ClassVar
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import Consulta, ResultadoPesquisa
from .parser import numero_paginas, parsear_pagina


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


TRIBUNAIS_CONFIG: dict[str, dict[str, str]] = {
    "tjsp": {
        "sigla": "TJSP",
        "nome": "Tribunal de Justiça de São Paulo",
        "base_url": "https://esaj.tjsp.jus.br/cjsg/",
        "uf": "SP",
    },
    "tjsc": {
        "sigla": "TJSC",
        "nome": "Tribunal de Justiça de Santa Catarina",
        "base_url": "https://esaj.tjsc.jus.br/cjsg/",
        "uf": "SC",
    },
    "tjms": {
        "sigla": "TJMS",
        "nome": "Tribunal de Justiça de Mato Grosso do Sul",
        "base_url": "https://esaj.tjms.jus.br/cjsg/",
        "uf": "MS",
    },
    "tjce": {
        "sigla": "TJCE",
        "nome": "Tribunal de Justiça do Ceará",
        "base_url": "https://esaj.tjce.jus.br/cjsg/",
        "uf": "CE",
    },
    "tjam": {
        "sigla": "TJAM",
        "nome": "Tribunal de Justiça do Amazonas",
        "base_url": "https://consultasaj.tjam.jus.br/cjsg/",
        "uf": "AM",
    },
    "tjal": {
        "sigla": "TJAL",
        "nome": "Tribunal de Justiça de Alagoas",
        "base_url": "https://www.tjal.jus.br/cjsg/",
        "uf": "AL",
    },
    "tjac": {
        "sigla": "TJAC",
        "nome": "Tribunal de Justiça do Acre",
        "base_url": "https://esaj.tjac.jus.br/cjsg/",
        "uf": "AC",
    },
}


class TJSPClient:
    BASE_URL = "https://esaj.tjsp.jus.br/cjsg/"
    TIPOS: ClassVar[dict[str, str]] = {
        "acordao": "A",
        "homologacao": "H",
        "monocratica": "D",
    }
    ORIGENS: ClassVar[dict[str, str]] = {
        "segundo_grau": "T",
        "colegio_recursal": "R",
    }

    def __init__(
        self,
        *,
        tribunal: str = "tjsp",
        base_url: str | None = None,
        intervalo: float = 2.0,
        timeout: float = 30.0,
        session: requests.Session | None = None,
        limitador: TokenBucket | None = None,
    ) -> None:
        if intervalo < 1.0:
            raise ValueError("Intervalo mínimo permitido é 1 segundo.")
        self.tribunal = tribunal.lower().strip()
        config_trib = TRIBUNAIS_CONFIG.get(self.tribunal, {})
        self.sigla = config_trib.get("sigla", self.tribunal.upper())
        self.base_url = base_url or config_trib.get("base_url", self.BASE_URL)
        self.timeout = timeout
        self.session = session or requests.Session()
        self._limitador = limitador or TokenBucket(intervalo)
        self._configurar_session()

    def pesquisar(
        self, consulta: Consulta, *, max_paginas: int = 1
    ) -> ResultadoPesquisa:
        consulta.validar()
        if max_paginas < 1:
            raise ValueError("max_paginas deve ser pelo menos 1.")

        tipo = self.TIPOS[consulta.tipo_decisao]
        corpo = self._corpo(consulta)
        self._requisicao("POST", "resultadoCompleta.do", data=corpo)

        decisoes = []
        total = 0
        paginas_coletadas = 0
        limite_real = max_paginas

        for pagina in range(1, max_paginas + 1):
            resposta = self._requisicao(
                "GET",
                "trocaDePagina.do",
                params={"tipoDeDecisao": tipo, "pagina": pagina, "conversationId": ""},
                headers={"Referer": f"{self.base_url}resultadoCompleta.do"},
            )
            total_pagina, itens = parsear_pagina(resposta.content)
            if pagina == 1:
                total = total_pagina
                limite_real = min(max_paginas, numero_paginas(total))
                if limite_real == 0:
                    break
            decisoes.extend(itens)
            paginas_coletadas += 1
            if pagina >= limite_real:
                break

        return ResultadoPesquisa(
            total_disponivel=total,
            paginas_coletadas=paginas_coletadas,
            decisoes=tuple(decisoes),
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
            destino.scheme != "https"
            or not (destino.hostname and "jus.br" in destino.hostname)
            or not destino.path.endswith("getArquivo.do")
        ):
            raise ValueError(f"URL de PDF fora do endpoint público permitido do tribunal ({url}).")
        return self._requisicao_url(
            "GET",
            url,
            stream=True,
            headers={"Accept": "application/pdf"},
        )

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
        tipo = self.TIPOS[consulta.tipo_decisao]
        origem = self.ORIGENS[consulta.origem]
        return {
            "dados.buscaInteiroTeor": consulta.pesquisa,
            "dados.pesquisarComSinonimos": "S" if consulta.pesquisar_sinonimos else "N",
            "dados.buscaEmenta": consulta.ementa,
            "dados.nuProcOrigem": "",
            "dados.nuRegistro": "",
            "agenteSelectedEntitiesList": "",
            "contadoragente": "0",
            "contadorMaioragente": "0",
            "codigoCr": "",
            "codigoTr": "",
            "nmAgente": "",
            "juizProlatorSelectedEntitiesList": "",
            "contadorjuizProlator": "0",
            "contadorMaiorjuizProlator": "0",
            "codigoJuizCr": "",
            "codigoJuizTr": "",
            "nmJuiz": "",
            "classesTreeSelection.values": consulta.classe,
            "classesTreeSelection.text": "",
            "assuntosTreeSelection.values": consulta.assunto,
            "assuntosTreeSelection.text": "",
            "comarcaSelectedEntitiesList": "",
            "contadorcomarca": "1" if consulta.comarca else "0",
            "contadorMaiorcomarca": "1" if consulta.comarca else "0",
            "cdComarca": consulta.comarca,
            "nmComarca": "",
            "secoesTreeSelection.values": consulta.orgao_julgador,
            "secoesTreeSelection.text": "",
            "dados.dtJulgamentoInicio": consulta.data_julgamento_inicio,
            "dados.dtJulgamentoFim": consulta.data_julgamento_fim,
            "dados.dtRegistroInicio": "",
            "dados.dtRegistroFim": "",
            "dados.ordenacao": "dtPublicacao",
            "dados.ordenarPor": "dtPublicacao",
            "dados.origensSelecionadas": origem,
            "tipoDecisaoSelecionados": tipo,
        }
