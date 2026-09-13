from __future__ import annotations

import sqlite3
from importlib.resources import files


def executar_migracoes(conexao: sqlite3.Connection) -> list[str]:
    """Executa migrações idempotentes no banco SQLite e retorna as aplicadas."""
    conexao.execute(
        """
        CREATE TABLE IF NOT EXISTS migracoes_schema (
            id TEXT PRIMARY KEY,
            aplicada_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    aplicadas_rows = conexao.execute("SELECT id FROM migracoes_schema").fetchall()
    aplicadas = {str(row[0]) for row in aplicadas_rows}

    novas_aplicadas: list[str] = []

    # Migração inicial 001_initial_schema
    migracao_001 = "001_initial_schema"
    if migracao_001 not in aplicadas:
        schema = (
            files("scraping_tjsp")
            .joinpath("schema_sqlite.sql")
            .read_text(encoding="utf-8")
        )
        conexao.executescript(schema)
        conexao.execute(
            "INSERT OR IGNORE INTO migracoes_schema (id) VALUES (?)",
            (migracao_001,),
        )
        novas_aplicadas.append(migracao_001)

    # Migração 002: Índices compostos adicionais para busca rápida
    migracao_002 = "002_add_search_composite_indexes"
    if migracao_002 not in aplicadas:
        conexao.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chunks_doc_busca
            ON chunks_documento (processamento_id, id);
            """
        )
        conexao.execute(
            "INSERT OR IGNORE INTO migracoes_schema (id) VALUES (?)",
            (migracao_002,),
        )
        novas_aplicadas.append(migracao_002)

    return novas_aplicadas
