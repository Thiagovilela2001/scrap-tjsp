from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from .db_pool import SQLiteConnectionPool
from .migrations import executar_migracoes
from .models import (
    Consulta,
    Decisao,
    ResultadoPesquisa,
)
from .settings import get_settings
from .storage_audit import AuditoriaStorageMixin
from .storage_documents import DocumentosStorageMixin
from .storage_lexical import LexicalStorageMixin, consulta_fts

_consulta_fts = consulta_fts


class RepositorioSQLite(
    AuditoriaStorageMixin, LexicalStorageMixin, DocumentosStorageMixin
):
    def __init__(
        self,
        caminho: Path | str | None = None,
        *,
        pool_size: int = 5,
    ) -> None:
        self.caminho = (
            Path(caminho) if caminho is not None else get_settings().sqlite_path
        )
        self._pool = SQLiteConnectionPool(self.caminho, tamanho_maximo=pool_size)

    def inicializar(self) -> list[str]:
        if str(self.caminho) != ":memory:":
            self.caminho.parent.mkdir(parents=True, exist_ok=True)
        with self._conectar() as conexao:
            return executar_migracoes(conexao)

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

    def listar_decisoes_consulta(self, consulta_id: int) -> tuple[Decisao, ...]:
        if consulta_id < 1:
            raise ValueError("consulta_id deve ser positivo.")
        with self._conectar() as conexao:
            consulta = conexao.execute(
                "SELECT 1 FROM consultas_jurisprudencia WHERE id = ?",
                (consulta_id,),
            ).fetchone()
            if consulta is None:
                raise LookupError(f"Consulta {consulta_id} não encontrada.")
            linhas = conexao.execute(
                """
                SELECT d.*
                FROM consulta_decisoes cd
                JOIN decisoes d ON d.id = cd.decisao_id
                WHERE cd.consulta_id = ?
                ORDER BY cd.posicao
                """,
                (consulta_id,),
            ).fetchall()
        return tuple(
            Decisao(
                processo=linha["processo"],
                cd_acordao=linha["cd_acordao"],
                cd_foro=linha["cd_foro"],
                classe=linha["classe"] or "",
                assunto=linha["assunto"] or "",
                relator=linha["relator"] or "",
                comarca=linha["comarca"] or "",
                orgao_julgador=linha["orgao_julgador"] or "",
                data_julgamento=_data_br(linha["data_julgamento"]),
                data_publicacao=_data_br(linha["data_publicacao"]),
                ementa=linha["ementa"] or "",
                inteiro_teor_url=linha["inteiro_teor_url"],
                ocorrencias=linha["ocorrencias"],
            )
            for linha in linhas
        )

    def obter_decisao(self, cd_acordao: str) -> Decisao | None:
        cd_acordao = cd_acordao.strip()
        if not cd_acordao.isdigit():
            return None
        with self._conectar() as conexao:
            linha = conexao.execute(
                "SELECT * FROM decisoes WHERE cd_acordao = ?",
                (cd_acordao,),
            ).fetchone()
        if linha is None:
            return None
        return Decisao(
            processo=linha["processo"],
            cd_acordao=linha["cd_acordao"],
            cd_foro=linha["cd_foro"],
            classe=linha["classe"] or "",
            assunto=linha["assunto"] or "",
            relator=linha["relator"] or "",
            comarca=linha["comarca"] or "",
            orgao_julgador=linha["orgao_julgador"] or "",
            data_julgamento=_data_br(linha["data_julgamento"]),
            data_publicacao=_data_br(linha["data_publicacao"]),
            ementa=linha["ementa"] or "",
            inteiro_teor_url=linha["inteiro_teor_url"],
            ocorrencias=linha["ocorrencias"],
        )

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
        with self._pool.conectar() as conexao:
            yield conexao

    def fechar(self) -> None:
        self._pool.fechar()

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


def _data_iso(valor: str) -> str | None:
    if not valor:
        return None
    try:
        data: date = datetime.strptime(valor, "%d/%m/%Y").date()
    except ValueError as exc:
        raise ValueError(f"Data devolvida pelo TJSP é inválida: {valor!r}.") from exc
    return data.isoformat()


def _data_br(valor: str | None) -> str:
    if not valor:
        return ""
    return datetime.strptime(valor, "%Y-%m-%d").strftime("%d/%m/%Y")
