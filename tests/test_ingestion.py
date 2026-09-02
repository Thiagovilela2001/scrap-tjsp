from pathlib import Path

import pytest

from scraping_tjsp.ingestion import ServicoColetaTJSP
from scraping_tjsp.models import (
    ChunkJuridico,
    Consulta,
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
        ementa="Responsabilidade civil.",
        inteiro_teor_url=(
            "https://esaj.tjsp.jus.br/cjsg/getArquivo.do"
            "?casChecked=true&cdAcordao=123&cdForo=0"
        ),
    )


class ClienteFalso:
    def __init__(self) -> None:
        self.paginas = None

    def pesquisar(self, consulta, *, max_paginas):
        self.paginas = max_paginas
        return ResultadoPesquisa(1, 1, (_decisao(),))


class DownloaderFalso:
    def baixar(self, decisao):
        return DocumentoBaixado(
            cd_acordao=decisao.cd_acordao,
            url_origem=decisao.inteiro_teor_url,
            caminho_local="data/pdfs/123.pdf",
            mime_type="application/pdf",
            tamanho_bytes=100,
            sha256="a" * 64,
        )


class ProcessadorFalso:
    def processar(self, documento):
        texto = "Fundamento jurídico indexado."
        return ResultadoProcessamento(
            cd_acordao=documento.cd_acordao,
            caminho_local=documento.caminho_local,
            sha256=documento.sha256,
            total_paginas=1,
            paginas=(PaginaExtraida(1, texto, "nativo"),),
            chunks=(ChunkJuridico(documento.cd_acordao, 1, 1, texto),),
            status="processado",
        )


class IndiceFalso:
    def __init__(self) -> None:
        self.itens = []

    def indexar_decisoes(self, decisoes):
        self.itens.extend(decisao.cd_acordao for decisao in decisoes)
        return len(decisoes)

    def indexar(self, processamento, decisao):
        self.itens.extend(chunk.identificador for chunk in processamento.chunks)
        return len(processamento.chunks)


def _servico(tmp_path: Path) -> tuple[ServicoColetaTJSP, RepositorioSQLite]:
    repositorio = RepositorioSQLite(tmp_path / "tjsp.sqlite3")
    repositorio.inicializar()
    return (
        ServicoColetaTJSP(
            repositorio,
            ClienteFalso(),
            DownloaderFalso(),
            ProcessadorFalso(),
            IndiceFalso(),
            IndiceFalso(),
            max_paginas=1,
            max_pdfs=1,
        ),
        repositorio,
    )


def test_pesquisa_persiste_e_importa_pdf_em_chunks(tmp_path: Path):
    servico, repositorio = _servico(tmp_path)

    pesquisa = servico.pesquisar(Consulta(pesquisa="contrato"), paginas=1)
    importacao = servico.importar(pesquisa["consulta_id"], ["123"])

    assert pesquisa["total_disponivel"] == 1
    assert pesquisa["ementas_indexadas"] == 1
    assert importacao["baixados"] == 1
    assert importacao["processados"] == 1
    assert importacao["chunks_indexados"] == 1
    assert importacao["erros"] == []
    assert repositorio.contagens_processamento()["chunks_documento"] == 1


def test_importacao_recusa_excesso_e_acordao_de_outra_consulta(tmp_path: Path):
    servico, _ = _servico(tmp_path)
    pesquisa = servico.pesquisar(Consulta(pesquisa="contrato"), paginas=1)

    with pytest.raises(ValueError, match="máximo"):
        servico.importar(pesquisa["consulta_id"], ["123", "456"])
    with pytest.raises(ValueError, match="não pertencem"):
        servico.importar(pesquisa["consulta_id"], ["456"])
