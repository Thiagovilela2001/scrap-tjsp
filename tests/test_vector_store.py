from pathlib import Path

from scraping_tjsp.models import (
    ChunkJuridico,
    Decisao,
    PaginaExtraida,
    ResultadoProcessamento,
)
from scraping_tjsp.vector_store import RepositorioChroma, RepositorioChunksChroma


class ColecaoFalsa:
    def __init__(self):
        self.lotes = []
        self.exclusoes = []

    def upsert(self, **kwargs):
        self.lotes.append(kwargs)

    def delete(self, **kwargs):
        self.exclusoes.append(kwargs)

    def count(self):
        return 1

    def query(self, **kwargs):
        return {
            "ids": [["acordao:123"]],
            "documents": [["Ementa sobre contrato."]],
            "metadatas": [[{"cd_acordao": "123"}]],
            "distances": [[0.1]],
        }


class ClienteFalso:
    def __init__(self):
        self.colecao = ColecaoFalsa()

    def get_or_create_collection(self, **kwargs):
        return self.colecao


def _decisao() -> Decisao:
    return Decisao(
        processo="1000123-45.2023.8.26.0100",
        cd_acordao="123",
        cd_foro="0",
        classe="Apelação Cível",
        assunto="Contratos",
        relator="Maria Silva",
        comarca="São Paulo",
        orgao_julgador="1ª Câmara",
        data_julgamento="01/08/2026",
        data_publicacao="02/08/2026",
        ementa="Ementa sobre contrato.",
        inteiro_teor_url="https://esaj.tjsp.jus.br/cjsg/getArquivo.do?casChecked=true",
        ocorrencias=3,
    )


def test_indexa_ementa_com_metadata(tmp_path: Path):
    cliente = ClienteFalso()
    repositorio = RepositorioChroma(tmp_path / "chroma", cliente=cliente)

    quantidade = repositorio.indexar_decisoes([_decisao()])

    assert quantidade == 1
    lote = cliente.colecao.lotes[0]
    assert lote["ids"] == ["acordao:123"]
    assert lote["documents"] == ["Ementa sobre contrato."]
    assert lote["metadatas"][0]["orgao_julgador"] == "1ª Câmara"
    assert lote["metadatas"][0]["ocorrencias"] == 3
    assert lote["metadatas"][0]["data_julgamento_ord"] == 20260801


def test_busca_semantica_normaliza_resultado(tmp_path: Path):
    repositorio = RepositorioChroma(tmp_path / "chroma", cliente=ClienteFalso())

    resultados = repositorio.buscar("quebra contratual")

    assert resultados[0]["id"] == "acordao:123"
    assert resultados[0]["distancia"] == 0.1


def test_indexa_chunks_com_citacao_verificavel(tmp_path: Path):
    cliente = ClienteFalso()
    repositorio = RepositorioChunksChroma(tmp_path / "chroma", cliente=cliente)
    resultado = ResultadoProcessamento(
        cd_acordao="123",
        caminho_local="data/pdfs/123.pdf",
        sha256="a" * 64,
        total_paginas=1,
        paginas=(PaginaExtraida(1, "Fundamenta\u00e7\u00e3o.", "nativo"),),
        chunks=(ChunkJuridico("123", 1, 1, "Fundamenta\u00e7\u00e3o."),),
        status="processado",
    )

    quantidade = repositorio.indexar(resultado, _decisao())

    assert quantidade == 1
    assert cliente.colecao.exclusoes == [{"where": {"cd_acordao": "123"}}]
    lote = cliente.colecao.lotes[0]
    assert lote["ids"] == ["acordao:123:pagina:1:chunk:1"]
    assert lote["metadatas"][0]["pagina"] == 1
    assert lote["metadatas"][0]["arquivo"] == "123.pdf"
    assert lote["metadatas"][0]["citacao"].endswith("p. 1")
