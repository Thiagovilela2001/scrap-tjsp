from __future__ import annotations

import queue
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class SQLiteConnectionPool:
    """Pool thread-safe de conexões SQLite com suporte a WAL e busy_timeout."""

    def __init__(
        self,
        caminho: Path | str,
        *,
        tamanho_maximo: int = 5,
        timeout: float = 30.0,
    ) -> None:
        self.caminho = Path(caminho) if str(caminho) != ":memory:" else caminho
        self.tamanho_maximo = max(1, tamanho_maximo)
        self.timeout = timeout
        self._fila: queue.Queue[sqlite3.Connection] = queue.Queue(
            maxsize=self.tamanho_maximo
        )
        self._total_criadas = 0
        self._lock = threading.Lock()
        self._fechado = False

    def _criar_conexao(self) -> sqlite3.Connection:
        conexao = sqlite3.connect(
            self.caminho,
            timeout=self.timeout,
            check_same_thread=False,
        )
        conexao.row_factory = sqlite3.Row
        conexao.execute("PRAGMA foreign_keys = ON")
        conexao.execute("PRAGMA busy_timeout = 30000")
        if str(self.caminho) != ":memory:":
            conexao.execute("PRAGMA journal_mode = WAL")
            conexao.execute("PRAGMA synchronous = NORMAL")
        return conexao

    def obter_conexao(self) -> sqlite3.Connection:
        if self._fechado:
            raise RuntimeError("Pool de conexões SQLite já foi encerrado.")

        try:
            return self._fila.get_nowait()
        except queue.Empty:
            pass

        with self._lock:
            if self._total_criadas < self.tamanho_maximo:
                conn = self._criar_conexao()
                self._total_criadas += 1
                return conn

        # Aguarda liberar uma conexão existente
        return self._fila.get(timeout=self.timeout)

    def devolver_conexao(self, conexao: sqlite3.Connection) -> None:
        if self._fechado:
            conexao.close()
            return

        try:
            self._fila.put_nowait(conexao)
        except queue.Full:
            conexao.close()
            with self._lock:
                self._total_criadas -= 1

    @contextmanager
    def conectar(self) -> Iterator[sqlite3.Connection]:
        conexao = self.obter_conexao()
        try:
            with conexao:
                yield conexao
        except Exception:
            try:
                conexao.rollback()
            except Exception:
                pass
            raise
        finally:
            self.devolver_conexao(conexao)

    def fechar(self) -> None:
        with self._lock:
            self._fechado = True
            while not self._fila.empty():
                try:
                    conn = self._fila.get_nowait()
                    conn.close()
                except queue.Empty:
                    break
            self._total_criadas = 0
