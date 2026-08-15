from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

from .models import (
    Consulta,
    Decisao,
    DocumentoBaixado,
    ResultadoPesquisa,
    ResultadoProcessamento,
)

if TYPE_CHECKING:
    from .rag import PacoteContextoIA, RespostaIA


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

    def iniciar_execucao_ia(
        self,
        pacote: PacoteContextoIA,
        *,
        provedor: str,
        modelo: str,
        configuracao: dict,
    ) -> int:
        with self._conectar() as conexao:
            cursor = conexao.execute(
                """
                INSERT INTO execucoes_ia
                    (pergunta, provedor, modelo, status, configuracao,
                     instrucoes_sistema, mensagem_usuario)
                VALUES (?, ?, ?, 'processando', ?, ?, ?)
                """,
                (
                    pacote.pergunta,
                    provedor,
                    modelo,
                    json.dumps(configuracao, ensure_ascii=False),
                    pacote.instrucoes_sistema,
                    pacote.mensagem_usuario,
                ),
            )
            execucao_id = int(cursor.lastrowid)
            conexao.executemany(
                """
                INSERT INTO fontes_execucao_ia
                    (execucao_id, posicao, chunk_id, citacao, url, texto,
                     score_hibrido)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        execucao_id,
                        fonte.numero,
                        fonte.id,
                        fonte.citacao,
                        fonte.url,
                        fonte.texto,
                        fonte.score_hibrido,
                    )
                    for fonte in pacote.fontes
                ),
            )
        return execucao_id

    def concluir_execucao_ia(self, execucao_id: int, resposta: RespostaIA) -> None:
        with self._conectar() as conexao:
            cursor = conexao.execute(
                """
                UPDATE execucoes_ia SET
                    status = 'concluida',
                    modelo = ?,
                    resposta = ?,
                    resposta_externa_id = ?,
                    tokens_entrada = ?,
                    tokens_saida = ?,
                    tokens_total = ?,
                    duracao_ms = ?,
                    erro = NULL,
                    concluido_em = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'processando'
                """,
                (
                    resposta.modelo,
                    resposta.texto,
                    resposta.resposta_id or None,
                    resposta.tokens_entrada,
                    resposta.tokens_saida,
                    resposta.tokens_total,
                    resposta.duracao_ms,
                    execucao_id,
                ),
            )
            if cursor.rowcount != 1:
                raise LookupError(
                    f"Execução de IA {execucao_id} não encontrada ou já finalizada."
                )

    def falhar_execucao_ia(
        self,
        execucao_id: int,
        erro: str,
        *,
        duracao_ms: int | None = None,
    ) -> None:
        with self._conectar() as conexao:
            cursor = conexao.execute(
                """
                UPDATE execucoes_ia SET
                    status = 'erro',
                    erro = ?,
                    duracao_ms = ?,
                    concluido_em = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'processando'
                """,
                (erro[:4000], duracao_ms, execucao_id),
            )
            if cursor.rowcount != 1:
                raise LookupError(
                    f"Execução de IA {execucao_id} não encontrada ou já finalizada."
                )

    def obter_execucao_ia(self, execucao_id: int) -> dict:
        with self._conectar() as conexao:
            execucao = conexao.execute(
                "SELECT * FROM execucoes_ia WHERE id = ?", (execucao_id,)
            ).fetchone()
            if execucao is None:
                raise LookupError(f"Execução de IA {execucao_id} não encontrada.")
            fontes = conexao.execute(
                """
                SELECT posicao, chunk_id, citacao, url, texto, score_hibrido
                FROM fontes_execucao_ia
                WHERE execucao_id = ?
                ORDER BY posicao
                """,
                (execucao_id,),
            ).fetchall()
        resultado = dict(execucao)
        resultado["configuracao"] = json.loads(resultado["configuracao"])
        resultado["fontes"] = [dict(fonte) for fonte in fontes]
        return resultado

    def listar_execucoes_ia(self, *, limite: int = 20) -> list[dict]:
        if limite < 1:
            raise ValueError("Limite deve ser pelo menos 1.")
        with self._conectar() as conexao:
            linhas = conexao.execute(
                """
                SELECT id, pergunta, provedor, modelo, status, resposta_externa_id,
                       tokens_entrada, tokens_saida, tokens_total, duracao_ms,
                       erro, criado_em, concluido_em
                FROM execucoes_ia
                ORDER BY id DESC
                LIMIT ?
                """,
                (limite,),
            ).fetchall()
        return [dict(linha) for linha in linhas]

    def registrar_avaliacao(
        self,
        relatorio: dict,
        *,
        dataset: str,
        configuracao: dict,
    ) -> int:
        resumo = relatorio.get("resumo", {})
        casos = relatorio.get("casos", [])
        with self._conectar() as conexao:
            cursor = conexao.execute(
                """
                INSERT INTO execucoes_avaliacao
                    (dataset, configuracao, resumo, aprovado)
                VALUES (?, ?, ?, ?)
                """,
                (
                    dataset,
                    json.dumps(configuracao, ensure_ascii=False),
                    json.dumps(resumo, ensure_ascii=False),
                    int(bool(resumo.get("aprovado"))),
                ),
            )
            avaliacao_id = int(cursor.lastrowid)
            conexao.executemany(
                """
                INSERT INTO casos_avaliacao
                    (avaliacao_id, caso_id, pergunta, resultado, aprovado)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    (
                        avaliacao_id,
                        caso["caso_id"],
                        caso["pergunta"],
                        json.dumps(caso, ensure_ascii=False),
                        int(bool(caso["aprovado"])),
                    )
                    for caso in casos
                ),
            )
        return avaliacao_id

    def contagens_auditoria(self) -> dict[str, int]:
        tabelas = (
            "execucoes_ia",
            "fontes_execucao_ia",
            "execucoes_avaliacao",
            "casos_avaliacao",
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
                documentos.caminho_local,
                documentos.sha256,
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
                "arquivo": Path(linha["caminho_local"]).name,
                "sha256": linha["sha256"],
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


def _data_br(valor: str | None) -> str:
    if not valor:
        return ""
    return datetime.strptime(valor, "%Y-%m-%d").strftime("%d/%m/%Y")


def _consulta_fts(texto: str) -> str:
    termos = re.findall(r"(?u)\b\w{2,}\b", texto.casefold())
    termos_unicos = list(dict.fromkeys(termos))[:32]
    if not termos_unicos:
        raise ValueError("Texto de busca não contém termos indexáveis.")
    return " OR ".join(f'"{termo}"' for termo in termos_unicos)
