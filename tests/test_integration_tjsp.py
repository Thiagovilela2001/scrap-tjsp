import pytest

from scraping_tjsp.client import TJSPClient
from scraping_tjsp.models import Consulta


@pytest.mark.integration
def test_portal_real_tjsp_devolve_decisoes_publicas():
    resultado = TJSPClient(intervalo=1.0).pesquisar(
        Consulta(pesquisa="dano moral"),
        max_paginas=1,
    )

    assert resultado.total_disponivel > 0
    assert resultado.paginas_coletadas == 1
    assert resultado.decisoes
    assert all(decisao.cd_acordao.isdigit() for decisao in resultado.decisoes)
