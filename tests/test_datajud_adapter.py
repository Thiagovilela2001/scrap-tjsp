import requests

from scraping_tjsp.adapters import DataJudAdapter
from scraping_tjsp.client import TJSPClient
from scraping_tjsp.models import Consulta


def _resposta_json(status: int, dados: dict) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r.headers["Content-Type"] = "application/json"
    import json

    r._content = json.dumps(dados).encode("utf-8")
    r._content_consumed = True
    return r


HIT_EXEMPLO = {
    "_id": "TJCE_123456",
    "_source": {
        "id": "123456",
        "numeroProcesso": "00702318020198060119",
        "classe": {"codigo": 198, "nome": "Apelação Cível"},
        "assuntos": [{"codigo": 10433, "nome": "Indenização por Dano Moral"}],
        "orgaoJulgador": {"codigo": 12, "nome": "3ª Câmara de Direito Privado"},
        "dataAjuizamento": "20240510123000",
        "dataHoraUltimaAtualizacao": "20240512140000",
        "movimentos": [
            {"codigo": 123, "nome": "Julgamento Concluído"},
            {"codigo": 456, "nome": "Acórdão Publicado"},
        ],
    },
}


def test_montar_query_elasticsearch():
    adapter = DataJudAdapter(sigla_tribunal="tjce")
    consulta = Consulta(
        pesquisa="dano moral",
        classe="Apelação",
        assunto="Indenização",
        orgao_julgador="3ª Câmara",
    )
    payload = adapter.montar_query_elasticsearch(consulta, pagina=2, tamanho=10)

    assert payload["from"] == 10
    assert payload["size"] == 10
    must = payload["query"]["bool"]["must"]
    assert any("multi_match" in clause for clause in must)
    assert any(
        clause.get("match", {}).get("classe.nome") == "Apelação" for clause in must
    )
    assert any(
        clause.get("match", {}).get("assuntos.nome") == "Indenização" for clause in must
    )


def test_parsear_hit_datajud():
    adapter = DataJudAdapter(sigla_tribunal="tjce")
    decisao = adapter._parsear_hit(HIT_EXEMPLO)

    assert decisao is not None
    assert decisao.processo == "00702318020198060119"
    assert decisao.cd_acordao == "123456"
    assert decisao.classe == "Apelação Cível"
    assert decisao.assunto == "Indenização por Dano Moral"
    assert decisao.orgao_julgador == "3ª Câmara de Direito Privado"
    assert decisao.data_julgamento == "10/05/2024"
    assert "Julgamento Concluído" in decisao.ementa
    assert decisao.inteiro_teor_url.endswith("/api_publica_tjce/_doc/TJCE_123456")


def test_formatar_data():
    assert DataJudAdapter._formatar_data("20240825123000") == "25/08/2024"
    assert DataJudAdapter._formatar_data("2024-08-25") == "25/08/2024"
    assert DataJudAdapter._formatar_data("") == ""


def test_pesquisar_datajud():
    chamadas = []

    def requisitar(metodo, url, **kwargs):
        chamadas.append((metodo, url, kwargs))
        return _resposta_json(
            200,
            {
                "hits": {
                    "total": {"value": 1},
                    "hits": [HIT_EXEMPLO],
                }
            },
        )

    adapter = DataJudAdapter(sigla_tribunal="tjce")
    resultado = adapter.pesquisar(
        requisitar, Consulta(pesquisa="dano moral"), max_paginas=1
    )

    assert resultado.total_disponivel == 1
    assert resultado.paginas_coletadas == 1
    assert len(resultado.decisoes) == 1
    assert resultado.decisoes[0].processo == "00702318020198060119"
    assert chamadas[0][0] == "POST"
    assert "api_publica_tjce/_search" in chamadas[0][1]
    assert "APIKey" in chamadas[0][2]["headers"]["Authorization"]


def test_tjsp_client_com_tribunal_datajud():
    cliente = TJSPClient(tribunal="datajud_tjce", intervalo=1.0)
    assert isinstance(cliente.adapter, DataJudAdapter)
    assert cliente.adapter.sigla_tribunal == "tjce"
    assert cliente.adapter.indice_tribunal == "api_publica_tjce"
