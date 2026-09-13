import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Lock
from types import SimpleNamespace

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


def test_tribunais_diferentes_consultam_em_paralelo(tmp_path, monkeypatch):
    servico, _ = _servico(tmp_path)
    barreira = Barrier(3, timeout=3)
    criados = []

    class ClienteConcorrente(ClienteFalso):
        def __init__(self, *, tribunal, intervalo, timeout):
            super().__init__()
            criados.append((tribunal, intervalo, timeout))

        def pesquisar(self, consulta, *, max_paginas):
            # Falha se um bloqueio global impedir a entrada dos três clientes.
            barreira.wait()
            return super().pesquisar(consulta, max_paginas=max_paginas)

    servico.cliente._limitador = SimpleNamespace(intervalo=2)
    servico.cliente.timeout = 17
    monkeypatch.setattr("scraping_tjsp.ingestion.TJSPClient", ClienteConcorrente)
    with ThreadPoolExecutor(max_workers=3) as executor:
        resultados = list(
            executor.map(
                lambda tribunal: servico.pesquisar(
                    Consulta(pesquisa="contrato"), tribunal=tribunal
                ),
                ["tjpr", "tjrs", "trf1"],
            )
        )
    assert all(resultado["total_disponivel"] == 1 for resultado in resultados)
    assert sorted(criados) == [("tjpr", 2, 17), ("tjrs", 2, 17), ("trf1", 2, 17)]


def test_mesmo_tribunal_reutiliza_cliente_sem_acesso_simultaneo(tmp_path, monkeypatch):
    servico, _ = _servico(tmp_path)
    criados = []
    ativos = 0
    max_ativos = 0
    contador = Lock()

    class ClienteMonitorado(ClienteFalso):
        def __init__(self, **kwargs):
            super().__init__()
            criados.append(self)

        def pesquisar(self, consulta, *, max_paginas):
            nonlocal ativos, max_ativos
            with contador:
                ativos += 1
                max_ativos = max(max_ativos, ativos)
            try:
                time.sleep(0.02)
                return super().pesquisar(consulta, max_paginas=max_paginas)
            finally:
                with contador:
                    ativos -= 1

    servico.cliente._limitador = SimpleNamespace(intervalo=2)
    servico.cliente.timeout = 17
    monkeypatch.setattr("scraping_tjsp.ingestion.TJSPClient", ClienteMonitorado)
    with ThreadPoolExecutor(max_workers=4) as executor:
        resultados = list(
            executor.map(
                lambda _: servico.pesquisar(
                    Consulta(pesquisa="contrato"), tribunal="tjpr"
                ),
                range(4),
            )
        )
    assert len(resultados) == 4
    assert len(criados) == 1
    assert max_ativos == 1
