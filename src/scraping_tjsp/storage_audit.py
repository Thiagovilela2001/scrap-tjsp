from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .rag import PacoteContextoIA, RespostaIA


class AuditoriaStorageMixin:
    """Mixin para operações de auditoria e telemetria de IA e avaliações."""

    def _conectar(self):
        raise NotImplementedError

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

