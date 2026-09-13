from __future__ import annotations

import re
from pathlib import Path


def consulta_fts(texto: str) -> str:
    termos = re.findall(r"(?u)\b\w{2,}\b", texto.casefold())
    termos_unicos = list(dict.fromkeys(termos))[:32]
    if not termos_unicos:
        raise ValueError("Texto de busca não contém termos indexáveis.")
    return " OR ".join(f'"{termo}"' for termo in termos_unicos)


class LexicalStorageMixin:
    """Mixin para operações de busca FTS5/BM25."""

    def _conectar(self):
        raise NotImplementedError

    def buscar_chunks_lexical(
        self,
        texto: str,
        *,
        limite: int = 30,
        filtros: dict[str, str | int] | None = None,
    ) -> list[dict]:
        if limite < 1:
            raise ValueError("Limite deve ser pelo menos 1.")
        c_fts = consulta_fts(texto)
        clausulas = ["chunks_fts MATCH ?"]
        parametros: list[str | int] = [c_fts]
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

