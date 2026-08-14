from __future__ import annotations

import time
from dataclasses import dataclass
from typing import ClassVar
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import Consulta, ResultadoPesquisa
from .parser import numero_paginas, parsear_pagina


@dataclass(slots=True)
class _Limitador:
    intervalo: float
    ultima_requisicao: float = 0.0

    def aguardar(self) -> None:
        restante = self.intervalo - (time.monotonic() - self.ultima_requisicao)
        if restante > 0:
            time.sleep(restante)

    def registrar(self) -> None:
        self.ultima_requisicao = time.monotonic()


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
        intervalo: float = 2.0,
        timeout: float = 30.0,
        session: requests.Session | None = None,
    ) -> None:
        if intervalo < 1.0:
            raise ValueError("Intervalo mínimo permitido é 1 segundo.")
        self.timeout = timeout
        self.session = session or requests.Session()
        self._limitador = _Limitador(intervalo)
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
                headers={"Referer": f"{self.BASE_URL}resultadoCompleta.do"},
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
            total=3,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            respect_retry_after_header=True,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retentativas))

    def _requisicao(self, metodo: str, caminho: str, **kwargs) -> requests.Response:
        return self._requisicao_url(metodo, f"{self.BASE_URL}{caminho}", **kwargs)

    def obter_pdf(self, url: str) -> requests.Response:
        destino = urlsplit(url)
        if (
            destino.scheme != "https"
            or destino.hostname != "esaj.tjsp.jus.br"
            or destino.path != "/cjsg/getArquivo.do"
        ):
            raise ValueError("URL de PDF fora do endpoint público permitido do TJSP.")
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
