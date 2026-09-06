import io
import zipfile

import pytest
import requests

from scraping_tjsp.adapters import TJPRAdapter
from scraping_tjsp.models import Consulta


def _resposta(url: str, conteudo: bytes, *, tipo: str = "text/html"):
    resposta = requests.Response()
    resposta.status_code = 200
    resposta.url = url
    resposta.headers["Content-Type"] = tipo
    resposta._content = conteudo
    resposta._content_consumed = True
    return resposta


HTML_FORMULARIO = b"""
<html><body>
  <form id="pesquisaForm" action="/jurisprudencia/publico/pesquisa.do?actionType=pesquisar"></form>
</body></html>
"""

HTML_RESULTADO = """
<html><body>
  <div>1 registro(s) encontrado(s), exibindo de 1 até 1</div>
  <table class="resultTable jurisprudencia">
    <tr class="even">
      <td class="juris-tabela-dados">
        <input name="idsSelecionados" value="4100000035672681">
        <div class="juris-tabela-propriedades">
          <a class="acordao" href="/jurisprudencia/j/4100000035672681/Acordao-0008930">
            0008930-18.2022.8.16.0033
          </a>
          (Acórdão) Relator: Maria Silva Processo: 0008930-18.2022.8.16.0033
          Órgão Julgador: 3ª Câmara Cível Data Julgamento: 01/09/2026
        </div>
      </td>
      <td class="juris-tabela-ementa">
        <div id="ementa4100000035672681">DANO MORAL CONFIGURADO.</div>
      </td>
    </tr>
  </table>
</body></html>
""".encode()


def test_pesquisa_e_parseia_portal_tjpr():
    chamadas = []

    def requisitar(metodo, url, **kwargs):
        chamadas.append((metodo, url, kwargs))
        if metodo == "GET":
            return _resposta("https://portal.tjpr.jus.br/jurisprudencia/", HTML_FORMULARIO)
        return _resposta(url, HTML_RESULTADO)

    resultado = TJPRAdapter(
        "https://portal.tjpr.jus.br/jurisprudencia/"
    ).pesquisar(requisitar, Consulta(pesquisa="dano moral"), max_paginas=1)

    assert resultado.total_disponivel == 1
    assert resultado.paginas_coletadas == 1
    assert resultado.decisoes[0].cd_acordao == "4100000035672681"
    assert resultado.decisoes[0].relator == "Maria Silva"
    assert resultado.decisoes[0].orgao_julgador == "3ª Câmara Cível"
    assert resultado.decisoes[0].inteiro_teor_url.startswith(
        "https://portal.tjpr.jus.br/jurisprudencia/j/"
    )
    assert chamadas[1][2]["data"]["idLocalPesquisa"] == "99"


def test_extrai_pdf_do_pacote_oficial_tjpr():
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as pacote:
        pacote.writestr("acordao.pdf", b"%PDF-1.4\nconteudo")

    detalhe = b"""
    <a href="javascript:document.location.replace('/jurisprudencia/publico/visualizacao.do?token=abc')">
      Carregar documento
    </a>
    """

    def requisitar(_metodo, url, **_kwargs):
        if "/j/" in url:
            return _resposta(url, detalhe)
        return _resposta(url, memoria.getvalue(), tipo="application/octet")

    resposta = TJPRAdapter(
        "https://portal.tjpr.jus.br/jurisprudencia/"
    ).obter_pdf(
        requisitar,
        "https://portal.tjpr.jus.br/jurisprudencia/j/123/Acordao-123",
    )

    assert resposta.headers["Content-Type"] == "application/pdf"
    assert resposta.content.startswith(b"%PDF-")


def test_recusa_url_externa_ao_baixar_inteiro_teor_tjpr():
    adapter = TJPRAdapter("https://portal.tjpr.jus.br/jurisprudencia/")

    with pytest.raises(ValueError, match="portal oficial"):
        adapter.obter_pdf(lambda *_args, **_kwargs: None, "https://exemplo.com/j/1")
