from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import DocumentoBaixado, ResultadoProcessamento


class DocumentosStorageMixin:
    """Mixin para persistência e consulta de documentos e processamentos de PDF."""

    def _conectar(self):
        raise NotImplementedError

    @staticmethod
    def _id_decisao(conexao: sqlite3.Connection, cd_acordao: str) -> int:
        raise NotImplementedError

    def obter_documento(self, cd_acordao: str) -> dict:
        cd_acordao = cd_acordao.strip()
        if not cd_acordao.isdigit():
            raise ValueError("Código de acórdão deve ser numérico.")
        with self._conectar() as conexao:
            linha = conexao.execute(
                """
                SELECT
                    documentos.id,
                    documentos.caminho_local,
                    documentos.mime_type,
                    documentos.tamanho_bytes,
                    documentos.sha256,
                    documentos.status,
                    documentos.url_origem,
                    decisoes.cd_acordao,
                    decisoes.processo
                FROM documentos
                JOIN decisoes ON decisoes.id = documentos.decisao_id
                WHERE decisoes.cd_acordao = ?
                """,
                (cd_acordao,),
            ).fetchone()
        if linha is None:
            raise LookupError(f"PDF do acórdão {cd_acordao} não encontrado.")
        return dict(linha)

    def registrar_documento(self, documento: DocumentoBaixado) -> None:
        with self._conectar() as conexao:
            decisao_id = self._id_decisao(conexao, documento.cd_acordao)
            conexao.execute(
                """
                INSERT INTO documentos
                    (decisao_id, url_origem, caminho_local, mime_type,
                     tamanho_bytes, sha256, status, erro, tentativas, baixado_em)
                VALUES (?, ?, ?, ?, ?, ?, 'baixado', NULL, 1, CURRENT_TIMESTAMP)
                ON CONFLICT (decisao_id) DO UPDATE SET
                    url_origem = excluded.url_origem,
                    caminho_local = excluded.caminho_local,
                    mime_type = excluded.mime_type,
                    tamanho_bytes = excluded.tamanho_bytes,
                    sha256 = excluded.sha256,
                    status = 'baixado',
                    erro = NULL,
                    tentativas = CASE
                        WHEN documentos.sha256 = excluded.sha256
                            THEN documentos.tentativas
                        ELSE documentos.tentativas + 1
                    END,
                    baixado_em = CURRENT_TIMESTAMP,
                    atualizado_em = CURRENT_TIMESTAMP
                """,
                (
                    decisao_id,
                    documento.url_origem,
                    documento.caminho_local,
                    documento.mime_type,
                    documento.tamanho_bytes,
                    documento.sha256,
                ),
            )

    def registrar_erro_download(
        self, cd_acordao: str, url: str, erro: str
    ) -> None:
        with self._conectar() as conexao:
            decisao_id = self._id_decisao(conexao, cd_acordao)
            conexao.execute(
                """
                INSERT INTO documentos
                    (decisao_id, url_origem, status, erro, tentativas)
                VALUES (?, ?, 'erro', ?, 1)
                ON CONFLICT (decisao_id) DO UPDATE SET
                    url_origem = excluded.url_origem,
                    status = 'erro',
                    erro = excluded.erro,
                    tentativas = documentos.tentativas + 1,
                    atualizado_em = CURRENT_TIMESTAMP
                """,
                (decisao_id, url, erro[:4000]),
            )

    def iniciar_processamento(self, cd_acordao: str) -> None:
        with self._conectar() as conexao:
            documento_id = self._id_documento(conexao, cd_acordao)
            conexao.execute(
                """
                INSERT INTO processamentos_documento (documento_id, status)
                VALUES (?, 'processando')
                ON CONFLICT (documento_id) DO UPDATE SET
                    status = 'processando',
                    erro = NULL,
                    tentativas = processamentos_documento.tentativas + 1,
                    iniciado_em = CURRENT_TIMESTAMP,
                    concluido_em = NULL,
                    atualizado_em = CURRENT_TIMESTAMP
                """,
                (documento_id,),
            )

    def registrar_processamento(
        self, resultado: ResultadoProcessamento
    ) -> None:
        with self._conectar() as conexao:
            documento_id = self._id_documento(conexao, resultado.cd_acordao)
            conexao.execute(
                """
                INSERT INTO processamentos_documento
                    (documento_id, status, total_paginas, paginas_com_texto,
                     paginas_ocr, total_chunks, erro, concluido_em)
                VALUES (?, ?, ?, ?, ?, ?, NULL, CURRENT_TIMESTAMP)
                ON CONFLICT (documento_id) DO UPDATE SET
                    status = excluded.status,
                    total_paginas = excluded.total_paginas,
                    paginas_com_texto = excluded.paginas_com_texto,
                    paginas_ocr = excluded.paginas_ocr,
                    total_chunks = excluded.total_chunks,
                    erro = NULL,
                    concluido_em = CURRENT_TIMESTAMP,
                    atualizado_em = CURRENT_TIMESTAMP
                """,
                (
                    documento_id,
                    resultado.status,
                    resultado.total_paginas,
                    resultado.paginas_com_texto,
                    resultado.paginas_ocr,
                    len(resultado.chunks),
                ),
            )
            processamento_id = self._id_processamento(conexao, documento_id)
            conexao.execute(
                "DELETE FROM paginas_documento WHERE processamento_id = ?",
                (processamento_id,),
            )
            conexao.execute(
                "DELETE FROM chunks_documento WHERE processamento_id = ?",
                (processamento_id,),
            )
            conexao.executemany(
                """
                INSERT INTO paginas_documento
                    (processamento_id, numero, texto, metodo, caracteres, erro)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        processamento_id,
                        pagina.numero,
                        pagina.texto,
                        pagina.metodo,
                        len(pagina.texto),
                        pagina.erro or None,
                    )
                    for pagina in resultado.paginas
                ),
            )
            conexao.executemany(
                """
                INSERT INTO chunks_documento
                    (id, processamento_id, pagina, indice, texto, caracteres)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        chunk.identificador,
                        processamento_id,
                        chunk.pagina,
                        chunk.indice,
                        chunk.texto,
                        len(chunk.texto),
                    )
                    for chunk in resultado.chunks
                ),
            )

    def registrar_erro_processamento(self, cd_acordao: str, erro: str) -> None:
        with self._conectar() as conexao:
            documento_id = self._id_documento(conexao, cd_acordao)
            conexao.execute(
                """
                INSERT INTO processamentos_documento
                    (documento_id, status, erro, concluido_em)
                VALUES (?, 'erro', ?, CURRENT_TIMESTAMP)
                ON CONFLICT (documento_id) DO UPDATE SET
                    status = 'erro',
                    erro = excluded.erro,
                    concluido_em = CURRENT_TIMESTAMP,
                    atualizado_em = CURRENT_TIMESTAMP
                """,
                (documento_id, erro[:4000]),
            )

    def contagens_processamento(self) -> dict[str, int]:
        tabelas = (
            "processamentos_documento",
            "paginas_documento",
            "chunks_documento",
        )
        with self._conectar() as conexao:
            return {
                tabela: int(
                    conexao.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]
                )
                for tabela in tabelas
            }

    @staticmethod
    def _id_documento(conexao: sqlite3.Connection, cd_acordao: str) -> int:
        resultado = conexao.execute(
            """
            SELECT documentos.id
            FROM documentos
            JOIN decisoes ON decisoes.id = documentos.decisao_id
            WHERE decisoes.cd_acordao = ? AND documentos.status = 'baixado'
            """,
            (cd_acordao,),
        ).fetchone()
        if resultado is None:
            raise LookupError(
                f"PDF baixado do acórdão {cd_acordao} não encontrado."
            )
        return int(resultado[0])

    @staticmethod
    def _id_processamento(conexao: sqlite3.Connection, documento_id: int) -> int:
        resultado = conexao.execute(
            "SELECT id FROM processamentos_documento WHERE documento_id = ?",
            (documento_id,),
        ).fetchone()
        if resultado is None:
            raise LookupError("Processamento de documento não encontrado.")
        return int(resultado[0])

