from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from importlib.resources import files
from pathlib import Path

from .models import (
    Consulta,
    Decisao,
    DocumentoBaixado,
    ResultadoPesquisa,
    ResultadoProcessamento,
)


class RepositorioSQLite:
    def __init__(self, caminho: Path | str = Path("data/tjsp.sqlite3")) -> None:
        self.caminho = Path(caminho)

    def inicializar(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        schema = (
            files("scraping_tjsp")
            .joinpath("schema_sqlite.sql")
            .read_text(encoding="utf-8")
        )
        with self._conectar() as conexao:
            conexao.executescript(schema)

    def salvar_pesquisa(self, consulta: Consulta, resultado: ResultadoPesquisa) -> int:
        with self._conectar() as conexao:
            cursor = conexao.execute(
                """
                INSERT INTO consultas_jurisprudencia
                    (parametros, total_disponivel, paginas_coletadas)
                VALUES (?, ?, ?)
                """,
                (
                    json.dumps(consulta.como_dict(), ensure_ascii=False),
                    resultado.total_disponivel,
                    resultado.paginas_coletadas,
                ),
            )
            consulta_id = int(cursor.lastrowid)
            for posicao, decisao in enumerate(resultado.decisoes, start=1):
                decisao_id = self._salvar_decisao(conexao, decisao)
                conexao.execute(
                    """
                    INSERT INTO consulta_decisoes (consulta_id, decisao_id, posicao)
                    VALUES (?, ?, ?)
                    ON CONFLICT (consulta_id, decisao_id)
                    DO UPDATE SET posicao = excluded.posicao
                    """,
                    (consulta_id, decisao_id, posicao),
                )
        return consulta_id

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

    def registrar_erro_download(self, cd_acordao: str, url: str, erro: str) -> None:
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

    def registrar_processamento(self, resultado: ResultadoProcessamento) -> None:
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

    def buscar_chunks_lexical(
        self,
        texto: str,
        *,
        limite: int = 30,
        filtros: dict[str, str | int] | None = None,
    ) -> list[dict]:
        if limite < 1:
            raise ValueError("Limite deve ser pelo menos 1.")
        consulta_fts = _consulta_fts(texto)
        clausulas = ["chunks_fts MATCH ?"]
        parametros: list[str | int] = [consulta_fts]
        colunas_filtro = {
            "cd_acordao": "decisoes.cd_acordao",
            "processo": "decisoes.processo",
            "classe": "decisoes.classe",
            "assunto": "decisoes.assunto",
            "orgao_julgador": "decisoes.orgao_julgador",
            "pagina": "chunks.pagina",
        }
        for chave, valor in (filtros or {}).items():
            coluna = colunas_filtro.get(chave)
            if coluna is None:
                raise ValueError(f"Filtro lexical não suportado: {chave!r}.")
            clausulas.append(f"{coluna} = ?")
            parametros.append(valor)
        parametros.append(limite)

        sql = f"""
            SELECT
                chunks.id,
                chunks.texto,
                chunks.pagina,
                chunks.indice,
                decisoes.cd_acordao,
                decisoes.cd_foro,
                decisoes.processo,
                decisoes.classe,
                decisoes.assunto,
                decisoes.relator,
                decisoes.comarca,
                decisoes.orgao_julgador,
                decisoes.data_julgamento,
                decisoes.data_publicacao,
                decisoes.inteiro_teor_url,
                bm25(chunks_fts) AS score_bm25
            FROM chunks_fts
            JOIN chunks_documento AS chunks ON chunks.rowid = chunks_fts.rowid
            JOIN processamentos_documento AS processamentos
                ON processamentos.id = chunks.processamento_id
            JOIN documentos ON documentos.id = processamentos.documento_id
            JOIN decisoes ON decisoes.id = documentos.decisao_id
            WHERE {" AND ".join(clausulas)}
            ORDER BY score_bm25
            LIMIT ?
        """
        with self._conectar() as conexao:
            linhas = conexao.execute(sql, parametros).fetchall()
        resultados = []
        for linha in linhas:
            metadata = {
                "cd_acordao": linha["cd_acordao"],
                "cd_foro": linha["cd_foro"],
                "processo": linha["processo"],
                "pagina": linha["pagina"],
                "indice_chunk": linha["indice"],
                "inteiro_teor_url": linha["inteiro_teor_url"],
                "tipo_registro": "inteiro_teor",
                "citacao": (
                    f"Processo {linha['processo']}, acórdão "
                    f"{linha['cd_acordao']}, p. {linha['pagina']}"
                ),
            }
            for chave in (
                "classe",
                "assunto",
                "relator",
                "comarca",
                "orgao_julgador",
                "data_julgamento",
                "data_publicacao",
            ):
                if linha[chave]:
                    metadata[chave] = linha[chave]
            resultados.append(
                {
                    "id": linha["id"],
                    "documento": linha["texto"],
                    "metadata": metadata,
                    "score_bm25": float(linha["score_bm25"]),
                }
            )
        return resultados

    def contagens(self) -> dict[str, int]:
        tabelas = ("consultas_jurisprudencia", "decisoes", "documentos")
        with self._conectar() as conexao:
            return {
                tabela: int(
                    conexao.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]
                )
                for tabela in tabelas
            }

    @contextmanager
    def _conectar(self) -> Iterator[sqlite3.Connection]:
        conexao = sqlite3.connect(self.caminho, timeout=30)
        conexao.row_factory = sqlite3.Row
        conexao.execute("PRAGMA foreign_keys = ON")
        conexao.execute("PRAGMA busy_timeout = 30000")
        try:
            with conexao:
                yield conexao
        finally:
            conexao.close()

    @staticmethod
    def _salvar_decisao(conexao: sqlite3.Connection, decisao: Decisao) -> int:
        conexao.execute(
            """
            INSERT INTO decisoes
                (cd_acordao, cd_foro, processo, classe, assunto, relator,
                 comarca, orgao_julgador, data_julgamento, data_publicacao,
                 ementa, inteiro_teor_url, ocorrencias)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (cd_acordao) DO UPDATE SET
                cd_foro = excluded.cd_foro,
                processo = excluded.processo,
                classe = excluded.classe,
                assunto = excluded.assunto,
                relator = excluded.relator,
                comarca = excluded.comarca,
                orgao_julgador = excluded.orgao_julgador,
                data_julgamento = excluded.data_julgamento,
                data_publicacao = excluded.data_publicacao,
                ementa = excluded.ementa,
                inteiro_teor_url = excluded.inteiro_teor_url,
                ocorrencias = excluded.ocorrencias,
                atualizado_em = CURRENT_TIMESTAMP
            """,
            (
                decisao.cd_acordao,
                decisao.cd_foro,
                decisao.processo,
                decisao.classe,
                decisao.assunto,
                decisao.relator,
                decisao.comarca,
                decisao.orgao_julgador,
                _data_iso(decisao.data_julgamento),
                _data_iso(decisao.data_publicacao),
                decisao.ementa,
                decisao.inteiro_teor_url,
                decisao.ocorrencias,
            ),
        )
        resultado = conexao.execute(
            "SELECT id FROM decisoes WHERE cd_acordao = ?", (decisao.cd_acordao,)
        ).fetchone()
        return int(resultado[0])

    @staticmethod
    def _id_decisao(conexao: sqlite3.Connection, cd_acordao: str) -> int:
        resultado = conexao.execute(
            "SELECT id FROM decisoes WHERE cd_acordao = ?", (cd_acordao,)
        ).fetchone()
        if resultado is None:
            raise LookupError(f"Decisão {cd_acordao} não encontrada.")
        return int(resultado[0])

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
                f"PDF baixado do ac\u00f3rd\u00e3o {cd_acordao} n\u00e3o encontrado."
            )
        return int(resultado[0])

    @staticmethod
    def _id_processamento(conexao: sqlite3.Connection, documento_id: int) -> int:
        resultado = conexao.execute(
            "SELECT id FROM processamentos_documento WHERE documento_id = ?",
            (documento_id,),
        ).fetchone()
        if resultado is None:
            raise LookupError("Processamento de documento n\u00e3o encontrado.")
        return int(resultado[0])


def _data_iso(valor: str) -> str | None:
    if not valor:
        return None
    try:
        data: date = datetime.strptime(valor, "%d/%m/%Y").date()
    except ValueError as exc:
        raise ValueError(f"Data devolvida pelo TJSP é inválida: {valor!r}.") from exc
    return data.isoformat()


def _consulta_fts(texto: str) -> str:
    termos = re.findall(r"(?u)\b\w{2,}\b", texto.casefold())
    termos_unicos = list(dict.fromkeys(termos))[:32]
    if not termos_unicos:
        raise ValueError("Texto de busca não contém termos indexáveis.")
    return " OR ".join(f'"{termo}"' for termo in termos_unicos)
