from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

import requests

from ..models import Consulta, Decisao, ResultadoPesquisa
from ..parser import numero_paginas, parsear_pagina


@dataclass(frozen=True, slots=True)
class ESAJCJSGAdapter:
    """Traduz consultas e resultados do portal e-SAJ/CJSG."""

    base_url: str

    TIPOS: ClassVar[dict[str, str]] = {
        "acordao": "A",
        "homologacao": "H",
        "monocratica": "D",
    }
    ORIGENS: ClassVar[dict[str, str]] = {
        "segundo_grau": "T",
        "colegio_recursal": "R",
    }

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", self.base_url.rstrip("/") + "/")

    def url(self, caminho: str) -> str:
        return f"{self.base_url}{caminho.lstrip('/')}"

    def corpo_consulta(self, consulta: Consulta) -> dict[str, str]:
        tipo = self.TIPOS[consulta.tipo_decisao]
        origem = self.ORIGENS[consulta.origem]
        return {
            "dados.buscaInteiroTeor": consulta.pesquisa,
            "dados.pesquisarComSinonimos": (
                "S" if consulta.pesquisar_sinonimos else "N"
            ),
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

    def parsear_resultados(self, html: str | bytes) -> tuple[int, list[Decisao]]:
        return parsear_pagina(
            html,
            inteiro_teor_base_url=self.url("getArquivo.do"),
        )

    def pesquisar(
        self,
        requisitar: Callable[..., requests.Response],
        consulta: Consulta,
        *,
        max_paginas: int,
    ) -> ResultadoPesquisa:
        tipo = self.TIPOS[consulta.tipo_decisao]
        requisitar(
            "POST",
            self.url("resultadoCompleta.do"),
            data=self.corpo_consulta(consulta),
        )

        decisoes: list[Decisao] = []
        total = 0
        paginas_coletadas = 0
        limite_real = max_paginas
        for pagina in range(1, max_paginas + 1):
            resposta = requisitar(
                "GET",
                self.url("trocaDePagina.do"),
                params={
                    "tipoDeDecisao": tipo,
                    "pagina": pagina,
                    "conversationId": "",
                },
                headers={"Referer": self.url("resultadoCompleta.do")},
            )
            total_pagina, itens = self.parsear_resultados(resposta.content)
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
