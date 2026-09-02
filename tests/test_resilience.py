from __future__ import annotations

import concurrent.futures
import time
from pathlib import Path

from scraping_tjsp.client import TJSPClient, TokenBucket
from scraping_tjsp.models import (
    ChunkJuridico,
    Decisao,
    PaginaExtraida,
    ResultadoProcessamento,
)
from scraping_tjsp.storage import RepositorioSQLite
from scraping_tjsp.vector_store import RepositorioChunksChroma


def test_token_bucket_initial_and_wait() -> None:
    bucket = TokenBucket(intervalo=1.0, capacidade=1.0, jitter_max=0.0)
    inicio = time.monotonic()
    bucket.aguardar(1.0)
    decorrido1 = time.monotonic() - inicio
    assert decorrido1 < 0.1

    # Segunda chamada consecutiva deve esperar ~1.0s
    inicio2 = time.monotonic()
    bucket.aguardar(1.0)
    decorrido2 = time.monotonic() - inicio2
    assert decorrido2 >= 0.85


def test_token_bucket_refill() -> None:
    bucket = TokenBucket(intervalo=1.0, capacidade=2.0, jitter_max=0.0)
    # Consumir 2 tokens imediatamente
    bucket.aguardar(2.0)
    assert bucket.tokens == 0.0

    # Esperar 0.5s -> recarrega ~0.5 tokens
    time.sleep(0.5)
    # Pedir 1 token -> deve esperar apenas ~0.5s restante
    inicio = time.monotonic()
    bucket.aguardar(1.0)
    decorrido = time.monotonic() - inicio
    assert 0.35 <= decorrido <= 0.85


def test_token_bucket_concurrency() -> None:
    bucket = TokenBucket(intervalo=1.0, capacidade=1.0, jitter_max=0.0)
    contagem = 0
    lock = concurrent.futures.ThreadPoolExecutor(max_workers=3)

    def trabalhador() -> None:
        nonlocal contagem
        bucket.aguardar(0.2)
        contagem += 1

    inicio = time.monotonic()
    with lock as executor:
        futuros = [executor.submit(trabalhador) for _ in range(5)]
        for f in futuros:
            f.result()
    decorrido = time.monotonic() - inicio
    assert contagem == 5
    # 5 consumos de 0.2 tokens = 1.0 token total -> roda rápido
    assert decorrido < 1.0


def test_tjsp_client_custom_limiter() -> None:
    bucket = TokenBucket(intervalo=1.0, capacidade=5.0, jitter_max=0.0)
    cliente = TJSPClient(intervalo=1.0, limitador=bucket)
    assert cliente._limitador is bucket


def test_sqlite_wal_mode(tmp_path: Path) -> None:
    db_path = tmp_path / "test_wal.sqlite3"
    repo = RepositorioSQLite(db_path)
    repo.inicializar()

    with repo._conectar() as conexao:
        modo = conexao.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(modo).lower() == "wal"
        busy = conexao.execute("PRAGMA busy_timeout").fetchone()[0]
        assert int(busy) == 30000


def test_chroma_batch_indexing(tmp_path: Path) -> None:
    chroma_dir = tmp_path / "chroma"
    repo = RepositorioChunksChroma(chroma_dir)

    decisao1 = Decisao(
        cd_acordao="1001",
        cd_foro="0001",
        processo="0000001-00.2026.8.26.0001",
        classe="Apelação",
        assunto="Indenização",
        relator="Desembargador A",
        comarca="São Paulo",
        orgao_julgador="1ª Câmara",
        data_julgamento="10/08/2026",
        data_publicacao="12/08/2026",
        ementa="Ementa caso 1",
        inteiro_teor_url="https://esaj.tjsp.jus.br/cjsg/getArquivo.do?cdAcordao=1001",
    )
    resultado1 = ResultadoProcessamento(
        cd_acordao="1001",
        caminho_local="data/pdfs/1001.pdf",
        sha256="abc1",
        total_paginas=1,
        paginas=(PaginaExtraida(numero=1, texto="Texto página 1 doc 1", metodo="nativo"),),
        chunks=(
            ChunkJuridico(
                cd_acordao="1001",
                pagina=1,
                indice=1,
                texto="Texto página 1 doc 1",
            ),
        ),
        status="processado",
    )

    decisao2 = Decisao(
        cd_acordao="1002",
        cd_foro="0001",
        processo="0000002-00.2026.8.26.0001",
        classe="Apelação",
        assunto="Indenização",
        relator="Desembargador B",
        comarca="Campinas",
        orgao_julgador="2ª Câmara",
        data_julgamento="11/08/2026",
        data_publicacao="13/08/2026",
        ementa="Ementa caso 2",
        inteiro_teor_url="https://esaj.tjsp.jus.br/cjsg/getArquivo.do?cdAcordao=1002",
    )
    resultado2 = ResultadoProcessamento(
        cd_acordao="1002",
        caminho_local="data/pdfs/1002.pdf",
        sha256="abc2",
        total_paginas=1,
        paginas=(PaginaExtraida(numero=1, texto="Texto página 1 doc 2", metodo="nativo"),),
        chunks=(
            ChunkJuridico(
                cd_acordao="1002",
                pagina=1,
                indice=1,
                texto="Texto página 1 doc 2",
            ),
        ),
        status="processado",
    )

    total_indexado = repo.indexar_lote([(resultado1, decisao1), (resultado2, decisao2)])
    assert total_indexado == 2

    busca = repo.buscar("Texto página 1 doc 1", limite=5)
    assert len(busca) >= 1
    assert any(b["id"] == "acordao:1001:pagina:1:chunk:1" for b in busca)
