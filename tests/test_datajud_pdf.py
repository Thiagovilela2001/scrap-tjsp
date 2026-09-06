from pathlib import Path

import pytest
import requests

from scraping_tjsp.adapters.datajud import DataJudAdapter
from scraping_tjsp.models import Decisao
from scraping_tjsp.storage import RepositorioSQLite


def test_datajud_adapter_obter_pdf():
    adapter = DataJudAdapter(
        base_url="https://api-publica.datajud.cnj.jus.br",
        api_key="teste_chave",
        sigla_tribunal="tjrj",
    )

    doc_fake = {
        "_source": {
            "numeroProcesso": "0001234-56.2026.8.19.0001",
            "tribunal": "TJRJ",
            "grau": "G2",
            "classe": {"nome": "Apelação Cível"},
            "orgaoJulgador": {"nome": "1ª Câmara Cível"},
            "assuntos": [{"nome": "Dano Moral"}],
            "dataAjuizamento": "2026-01-10T10:00:00.000Z",
            "movimentos": [
                {
                    "nome": "Julgamento",
                    "dataHora": "2026-02-01T14:00:00.000Z",
                    "complementosTabelados": [{"nome": "Acórdão proferido"}],
                }
            ],
        }
    }

    def requisitar_fake(metodo, url, **kwargs):
        resp = requests.Response()
        resp.status_code = 200
        resp.url = url
        resp._content = requests.compat.json.dumps(doc_fake).encode("utf-8")
        return resp

    resposta = adapter.obter_pdf(
        requisitar_fake,
        "https://api-publica.datajud.cnj.jus.br/api_publica_tjrj/_doc/fake123",
    )

    assert resposta.status_code == 200
    assert resposta.headers["Content-Type"] == "application/pdf"
    assert resposta.content.startswith(b"%PDF-")
    assert len(resposta.content) > 500


def test_datajud_recusa_url_invalida():
    adapter = DataJudAdapter(
        base_url="https://api-publica.datajud.cnj.jus.br",
        api_key="teste_chave",
        sigla_tribunal="tjrj",
    )
    with pytest.raises(ValueError, match="fora da API pública"):
        adapter.obter_pdf(lambda *args, **kwargs: None, "https://exemplo.com/doc")


def test_storage_obter_decisao(tmp_path: Path):
    repo = RepositorioSQLite(tmp_path / "t.sqlite3")
    repo.inicializar()

    decisao = Decisao(
        processo="12345-00.2026.8.19.0001",
        cd_acordao="987654321",
        cd_foro="0",
        classe="Apelação",
        assunto="Civil",
        relator="Relator Teste",
        comarca="Rio de Janeiro",
        orgao_julgador="2ª Câmara Cível",
        data_julgamento="01/02/2026",
        data_publicacao="02/02/2026",
        ementa="Ementa de teste TJRJ",
        inteiro_teor_url="https://api-publica.datajud.cnj.jus.br/api_publica_tjrj/_doc/teste",
    )

    from scraping_tjsp.models import Consulta, ResultadoPesquisa

    repo.salvar_pesquisa(
        Consulta(pesquisa="teste"),
        ResultadoPesquisa(total_disponivel=1, paginas_coletadas=1, decisoes=(decisao,)),
    )

    recuperada = repo.obter_decisao("987654321")
    assert recuperada is not None
    assert recuperada.cd_acordao == "987654321"
    assert recuperada.processo == "12345-00.2026.8.19.0001"
    assert recuperada.orgao_julgador == "2ª Câmara Cível"
    assert repo.obter_decisao("000000000") is None
