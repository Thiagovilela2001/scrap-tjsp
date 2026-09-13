import sqlite3
from pathlib import Path

from scraping_tjsp.migrations import executar_migracoes
from scraping_tjsp.storage import RepositorioSQLite


def test_migrations_idempotent(tmp_path: Path):
    caminho = tmp_path / "migracoes_teste.sqlite3"
    with sqlite3.connect(caminho) as conn:
        aplicadas_1 = executar_migracoes(conn)
        assert "001_initial_schema" in aplicadas_1
        assert "002_add_search_composite_indexes" in aplicadas_1

        aplicadas_2 = executar_migracoes(conn)
        assert aplicadas_2 == []


def test_repositorio_inicializar_aplica_migracoes(tmp_path: Path):
    caminho = tmp_path / "repo_migracoes.sqlite3"
    repo = RepositorioSQLite(caminho)
    aplicadas = repo.inicializar()
    assert len(aplicadas) >= 2

    # Segunda inicialização não repete
    aplicadas_novas = repo.inicializar()
    assert aplicadas_novas == []
    repo.fechar()
