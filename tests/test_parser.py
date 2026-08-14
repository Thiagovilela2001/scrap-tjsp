from scraping_tjsp.parser import numero_paginas, parsear_pagina

HTML = """
<html><body>
  <input id="totalResultadoAbaRetornoFiltro-A" value="21">
  <table>
    <tr class="fundocinza1">
      <td>1 -</td>
      <td><table>
        <tr class="ementaClass"><td>
          <a class="esajLinkLogin downloadEmenta" cdacordao="123" cdforo="0">
            1000123-45.2023.8.26.0100
          </a>
          <span class="segredoJustica">(7 ocorrências encontradas)</span>
        </td></tr>
        <tr class="ementaClass2"><td><strong>Classe/Assunto:</strong> Apelação Cível / Contratos</td></tr>
        <tr class="ementaClass2"><td><strong>Relator(a):</strong> Maria Silva</td></tr>
        <tr class="ementaClass2"><td><strong>Comarca:</strong> São Paulo</td></tr>
        <tr class="ementaClass2"><td><strong>Órgão julgador:</strong> 1ª Câmara</td></tr>
        <tr class="ementaClass2"><td><strong>Data do julgamento:</strong> 01/08/2026</td></tr>
        <tr class="ementaClass2"><td><strong>Data de publicação:</strong> 02/08/2026</td></tr>
        <tr class="ementaClass2"><td>
          <div align="justify"><strong>Ementa:</strong> Texto curto...</div>
          <div align="justify" style="display: none"><strong>Ementa:</strong> Texto completo da decisão.</div>
        </td></tr>
      </table></td>
    </tr>
  </table>
</body></html>
"""


def test_parseia_resultado_e_prefere_ementa_completa():
    total, decisoes = parsear_pagina(HTML)
    decisao = decisoes[0]

    assert total == 21
    assert decisao.processo == "1000123-45.2023.8.26.0100"
    assert decisao.classe == "Apelação Cível"
    assert decisao.assunto == "Contratos"
    assert decisao.orgao_julgador == "1ª Câmara"
    assert decisao.ementa == "Texto completo da decisão."
    assert decisao.ocorrencias == 7
    assert "casChecked=true" in decisao.inteiro_teor_url
    assert decisao.inteiro_teor_url.endswith("cdAcordao=123&cdForo=0")


def test_calcula_paginas():
    assert numero_paginas(0) == 0
    assert numero_paginas(20) == 1
    assert numero_paginas(21) == 2


def test_recusa_pagina_de_consulta():
    html = '<form name="consultaCompletaForm"></form>'
    try:
        parsear_pagina(html)
    except RuntimeError as exc:
        assert "pesquisa não foi aceita" in str(exc)
    else:
        raise AssertionError("Era esperado RuntimeError")
