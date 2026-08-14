from pathlib import Path

import pytest

from scraping_tjsp.dataset import (
    FonteDataset,
    PreparadorDataset,
    carregar_fontes_dataset,
)
from scraping_tjsp.models import (
    ChunkJuridico,
    DocumentoBaixado,
    PaginaExtraida,
    ResultadoProcessamento,
)
from scraping_tjsp.storage import RepositorioSQLite


def _fonte() -> FonteDataset:
    return FonteDataset.de_dict(
        {
            "caso_id": "caso-123",
            "processo": "1000123-45.2023.8.26.0100",
            "acordaos_relevantes": ["123"],
            "fonte_url": (
                "https://esaj.tjsp.jus.br/cjsg/getArquivo.do"
                "?casChecked=true&cdAcordao=123&cdForo=0"
            ),
        }
    )


class DownloaderFalso:
    def baixar(self, decisao):
        return DocumentoBaixado(
            cd_acordao=decisao.cd_acordao,
            url_origem=decisao.inteiro_teor_url,
            caminho_local="pdfs/123.pdf",
            mime_type="application/pdf",
            tamanho_bytes=100,
            sha256="a" * 64,
        )


class ProcessadorFalso:
    def processar(self, documento):
        texto = "Texto jurídico da decisão para indexação."
        return ResultadoProcessamento(
            cd_acordao=documento.cd_acordao,
            caminho_local=documento.caminho_local,
            sha256=documento.sha256,
            total_paginas=1,
            paginas=(PaginaExtraida(1, texto, "nativo"),),
            chunks=(ChunkJuridico(documento.cd_acordao, 1, 1, texto),),
            status="processado",
        )


class ChromaFalso:
    def __init__(self):
        self.ids = []

    def indexar(self, resultado, decisao):
        self.ids.extend(chunk.identificador for chunk in resultado.chunks)
        return len(resultado.chunks)


def test_carrega_dataset_real_com_fontes_oficiais_unicas():
    caminho = Path(__file__).parents[1] / "evals" / "casos.jsonl"

    fontes = carregar_fontes_dataset(caminho)

    assert len(fontes) == 20
    assert len({fonte.cd_acordao for fonte in fontes}) == 20
    assert all(fonte.cd_foro == "0" for fonte in fontes)


def test_recusa_url_que_nao_corresponde_ao_acordao():
    with pytest.raises(ValueError, match="não corresponde"):
        FonteDataset.de_dict(
            {
                "caso_id": "invalido",
                "processo": "1",
                "acordaos_relevantes": ["123"],
                "fonte_url": (
                    "https://esaj.tjsp.jus.br/cjsg/getArquivo.do"
                    "?casChecked=true&cdAcordao=456&cdForo=0"
                ),
            }
        )


def test_prepara_fonte_no_sqlite_e_chroma(tmp_path: Path):
    repositorio = RepositorioSQLite(tmp_path / "dataset.sqlite3")
    chroma = ChromaFalso()
    preparador = PreparadorDataset(
        repositorio,
        DownloaderFalso(),
        ProcessadorFalso(),
        chroma,
    )

    resultado = preparador.preparar((_fonte(),), nome_dataset="teste.jsonl")

    assert resultado.aprovado
    assert resultado.baixados == 1
    assert resultado.processados == 1
    assert resultado.chunks_indexados == 1
    assert chroma.ids == ["acordao:123:pagina:1:chunk:1"]
    assert repositorio.contagens() == {
        "consultas_jurisprudencia": 1,
        "decisoes": 1,
        "documentos": 1,
    }
