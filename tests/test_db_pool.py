import concurrent.futures
from pathlib import Path

from scraping_tjsp.db_pool import SQLiteConnectionPool


def test_sqlite_connection_pool_basic(tmp_path: Path):
    caminho = tmp_path / "pool_teste.sqlite3"
    pool = SQLiteConnectionPool(caminho, tamanho_maximo=3)

    with pool.conectar() as conn:
        conn.execute("CREATE TABLE teste (id INTEGER PRIMARY KEY, valor TEXT)")
        conn.execute("INSERT INTO teste (valor) VALUES ('ok')")

    with pool.conectar() as conn:
        row = conn.execute("SELECT valor FROM teste WHERE id = 1").fetchone()
        assert row["valor"] == "ok"

    pool.fechar()


def test_sqlite_connection_pool_concurrent_access(tmp_path: Path):
    caminho = tmp_path / "pool_concorrente.sqlite3"
    pool = SQLiteConnectionPool(caminho, tamanho_maximo=5)

    with pool.conectar() as conn:
        conn.execute("CREATE TABLE contadores (thread_id INT, valor INT)")

    def inserir_dados(thread_idx: int):
        with pool.conectar() as conn:
            conn.execute(
                "INSERT INTO contadores (thread_id, valor) VALUES (?, ?)",
                (thread_idx, thread_idx * 10),
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        list(executor.map(inserir_dados, range(20)))

    with pool.conectar() as conn:
        count = conn.execute("SELECT count(*) FROM contadores").fetchone()[0]
        assert count == 20

    pool.fechar()
