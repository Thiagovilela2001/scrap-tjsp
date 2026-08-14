import sqlite3
from pathlib import Path

from scraping_tjsp import Consulta
from scraping_tjsp.models import (
    ChunkJuridico,
    Decisao,
    DocumentoBaixado,
    PaginaExtraida,
    ResultadoPesquisa,
    ResultadoProcessamento,
)
from scraping_tjsp.storage import RepositorioSQLite


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
        ementa="Texto.",
        inteiro_teor_url="https://esaj.tjsp.jus.br/cjsg/getArquivo.do?casChecked=true",
    )


def test_persistencia_sqlite_real_e_idempotente(tmp_path: Path):
    caminho = tmp_path / "tjsp.sqlite3"
    repositorio = RepositorioSQLite(caminho)
    repositorio.inicializar()
    resultado = ResultadoPesquisa(1, 1, (_decisao(),))

    primeiro_id = repositorio.salvar_pesquisa(Consulta(pesquisa="contrato"), resultado)
    segundo_id = repositorio.salvar_pesquisa(Consulta(pesquisa="contrato"), resultado)

    assert primeiro_id == 1
    assert segundo_id == 2
    assert repositorio.contagens() == {
        "consultas_jurisprudencia": 2,
        "decisoes": 1,
        "documentos": 0,
    }
    with sqlite3.connect(caminho) as conexao:
        data = conexao.execute(
            "SELECT data_julgamento FROM decisoes WHERE cd_acordao = '123'"
        ).fetchone()[0]
    assert data == "2026-08-01"


def test_registra_documento_no_sqlite(tmp_path: Path):
    repositorio = RepositorioSQLite(tmp_path / "tjsp.sqlite3")
    repositorio.inicializar()
    repositorio.salvar_pesquisa(
        Consulta(pesquisa="contrato"), ResultadoPesquisa(1, 1, (_decisao(),))
    )
    repositorio.registrar_documento(
        DocumentoBaixado(
            cd_acordao="123",
            url_origem=_decisao().inteiro_teor_url,
            caminho_local="data/pdfs/123.pdf",
            mime_type="application/pdf",
            tamanho_bytes=100,
            sha256="a" * 64,
        )
    )

    assert repositorio.contagens()["documentos"] == 1


def test_persiste_paginas_chunks_e_reprocessamento(tmp_path: Path):
    repositorio = RepositorioSQLite(tmp_path / "tjsp.sqlite3")
    repositorio.inicializar()
    repositorio.salvar_pesquisa(
        Consulta(pesquisa="contrato"), ResultadoPesquisa(1, 1, (_decisao(),))
    )
    documento = DocumentoBaixado(
        cd_acordao="123",
        url_origem=_decisao().inteiro_teor_url,
        caminho_local="data/pdfs/123.pdf",
        mime_type="application/pdf",
        tamanho_bytes=100,
        sha256="a" * 64,
    )
    repositorio.registrar_documento(documento)
    resultado = ResultadoProcessamento(
        cd_acordao="123",
        caminho_local=documento.caminho_local,
        sha256=documento.sha256,
        total_paginas=1,
        paginas=(PaginaExtraida(1, "Texto da p\u00e1gina.", "nativo"),),
        chunks=(ChunkJuridico("123", 1, 1, "Texto da p\u00e1gina."),),
        status="processado",
    )

    repositorio.iniciar_processamento("123")
    repositorio.registrar_processamento(resultado)
    repositorio.inicializar()
    repositorio.iniciar_processamento("123")
    repositorio.registrar_processamento(resultado)

    assert repositorio.contagens_processamento() == {
        "processamentos_documento": 1,
        "paginas_documento": 1,
        "chunks_documento": 1,
    }
    with sqlite3.connect(repositorio.caminho) as conexao:
        status, tentativas = conexao.execute(
            "SELECT status, tentativas FROM processamentos_documento"
        ).fetchone()
    assert status == "processado"
    assert tentativas == 2

    encontrados = repositorio.buscar_chunks_lexical("pagina", limite=5)
    assert [item["id"] for item in encontrados] == ["acordao:123:pagina:1:chunk:1"]
    assert encontrados[0]["metadata"]["citacao"].endswith("p. 1")
