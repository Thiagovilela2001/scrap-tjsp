import pytest
from scraping_tjsp.adapters.stf import STFAdapter, converter_hit_stf
from scraping_tjsp.models import Decisao


def test_converter_hit_stf_completo():
    hit = {
        "id": "repercussao-geral8442",
        "processo_codigo_completo": "ARE 945271 RG",
        "processo_classe_processual_unificada_classe_sigla": "ARE",
        "ministro_facet": ["GILMAR MENDES"],
        "orgao_julgador": "Tribunal Pleno",
        "julgamento_data": "2016-03-03",
        "publicacao_data": "2016-03-16",
        "ementa_texto": "Recurso extraordinário com agravo. Repercussão geral reconhecida.",
        "inteiro_teor_url": "https://portal.stf.jus.br/jurisprudencia/obterInteiroTeor.asp?idDocumento=10499696",
    }
    decisao = converter_hit_stf(hit)
    assert isinstance(decisao, Decisao)
    assert decisao.processo == "ARE 945271 RG"
    assert decisao.classe == "ARE"
    assert decisao.relator == "GILMAR MENDES"
    assert decisao.orgao_julgador == "Tribunal Pleno"
    assert decisao.data_julgamento == "03/03/2016"
    assert decisao.data_publicacao == "16/03/2016"
    assert "Repercussão geral" in decisao.ementa
    assert decisao.inteiro_teor_url == "https://portal.stf.jus.br/jurisprudencia/obterInteiroTeor.asp?idDocumento=10499696"


def test_converter_hit_stf_minimo():
    hit = {
        "titulo": "RE 123456",
        "ementa_texto": "Ementa simples",
    }
    decisao = converter_hit_stf(hit)
    assert decisao.processo == "RE 123456"
    assert decisao.ementa == "Ementa simples"
    assert decisao.relator == ""
    assert decisao.orgao_julgador == "Supremo Tribunal Federal"


def test_stf_adapter_url():
    adapter = STFAdapter()
    assert adapter.url() == "https://jurisprudencia.stf.jus.br/pages/search"
    assert adapter.url("api/search") == "https://jurisprudencia.stf.jus.br/api/search"
