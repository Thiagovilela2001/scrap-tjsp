from __future__ import annotations

from datetime import datetime
from pathlib import Path

import chromadb

from .models import ChunkJuridico, Decisao, ResultadoProcessamento

MODELO_EMBEDDING_PADRAO = "all-MiniLM-L6-v2"


class RepositorioChroma:
    NOME_COLECAO = "ementas_tjsp"

    def __init__(
        self,
        caminho: Path | str = Path("data/chroma"),
        *,
        cliente=None,
        modelo_embedding: str = MODELO_EMBEDDING_PADRAO,
        embedding_function=None,
    ) -> None:
        self.caminho = Path(caminho)
        self.caminho.mkdir(parents=True, exist_ok=True)
        self.modelo_embedding = modelo_embedding
        self.cliente = cliente or chromadb.PersistentClient(path=str(self.caminho))
        self.colecao = _obter_colecao(
            self.cliente,
            self.NOME_COLECAO,
            modelo_embedding,
            embedding_function,
            {
                "descricao": "Ementas públicas coletadas no TJSP/CJSG",
                "hnsw:space": "cosine",
            },
        )

    def indexar_decisoes(self, decisoes: tuple[Decisao, ...] | list[Decisao]) -> int:
        indexaveis = [decisao for decisao in decisoes if decisao.ementa.strip()]
        for inicio in range(0, len(indexaveis), 100):
            lote = indexaveis[inicio : inicio + 100]
            self.colecao.upsert(
                ids=[f"acordao:{decisao.cd_acordao}" for decisao in lote],
                documents=[decisao.ementa for decisao in lote],
                metadatas=[_metadata(decisao) for decisao in lote],
            )
        return len(indexaveis)

    def buscar(
        self,
        texto: str,
        *,
        limite: int = 10,
        filtros: dict | None = None,
    ) -> list[dict]:
        if not texto.strip():
            raise ValueError("Texto de busca não pode ser vazio.")
        if limite < 1:
            raise ValueError("Limite deve ser pelo menos 1.")
        quantidade = self.colecao.count()
        if quantidade == 0:
            return []
        parametros = {
            "query_texts": [texto],
            "n_results": min(limite, quantidade),
            "include": ["documents", "metadatas", "distances"],
        }
        if filtros:
            parametros["where"] = filtros
        resultado = self.colecao.query(
            **parametros,
        )
        ids = resultado.get("ids", [[]])[0]
        documentos = resultado.get("documents", [[]])[0]
        metadatas = resultado.get("metadatas", [[]])[0]
        distancias = resultado.get("distances", [[]])[0]
        return [
            {
                "id": identificador,
                "documento": documento,
                "metadata": metadata,
                "distancia": distancia,
            }
            for identificador, documento, metadata, distancia in zip(
                ids, documentos, metadatas, distancias, strict=True
            )
        ]


class RepositorioChunksChroma:
    NOME_COLECAO = "chunks_tjsp"

    def __init__(
        self,
        caminho: Path | str = Path("data/chroma"),
        *,
        cliente=None,
        modelo_embedding: str = MODELO_EMBEDDING_PADRAO,
        embedding_function=None,
    ) -> None:
        self.caminho = Path(caminho)
        self.caminho.mkdir(parents=True, exist_ok=True)
        self.modelo_embedding = modelo_embedding
        self.cliente = cliente or chromadb.PersistentClient(path=str(self.caminho))
        self.colecao = _obter_colecao(
            self.cliente,
            self.NOME_COLECAO,
            modelo_embedding,
            embedding_function,
            {
                "descricao": "Trechos por p\u00e1gina dos inteiros teores do TJSP/CJSG",
                "hnsw:space": "cosine",
            },
        )

    def indexar(
        self,
        resultado: ResultadoProcessamento,
        decisao: Decisao,
    ) -> int:
        chunks = list(resultado.chunks)
        self.colecao.delete(where={"cd_acordao": resultado.cd_acordao})
        for inicio in range(0, len(chunks), 100):
            lote = chunks[inicio : inicio + 100]
            self.colecao.upsert(
                ids=[chunk.identificador for chunk in lote],
                documents=[chunk.texto for chunk in lote],
                metadatas=[
                    _metadata_chunk(chunk, resultado, decisao) for chunk in lote
                ],
            )
        return len(chunks)

    def buscar(
        self,
        texto: str,
        *,
        limite: int = 10,
        filtros: dict | None = None,
    ) -> list[dict]:
        if not texto.strip():
            raise ValueError("Texto de busca n\u00e3o pode ser vazio.")
        if limite < 1:
            raise ValueError("Limite deve ser pelo menos 1.")
        quantidade = self.colecao.count()
        if quantidade == 0:
            return []
        parametros = {
            "query_texts": [texto],
            "n_results": min(limite, quantidade),
            "include": ["documents", "metadatas", "distances"],
        }
        if filtros:
            parametros["where"] = filtros
        resultado = self.colecao.query(**parametros)
        return [
            {
                "id": identificador,
                "documento": documento,
                "metadata": metadata,
                "distancia": distancia,
            }
            for identificador, documento, metadata, distancia in zip(
                resultado.get("ids", [[]])[0],
                resultado.get("documents", [[]])[0],
                resultado.get("metadatas", [[]])[0],
                resultado.get("distances", [[]])[0],
                strict=True,
            )
        ]


def criar_funcao_embedding(modelo: str):
    modelo = modelo.strip()
    if not modelo or modelo == MODELO_EMBEDDING_PADRAO:
        return None
    try:
        from chromadb.utils.embedding_functions import (
            SentenceTransformerEmbeddingFunction,
        )

        return SentenceTransformerEmbeddingFunction(
            model_name=modelo,
            device="cpu",
            normalize_embeddings=True,
        )
    except ValueError as exc:
        raise RuntimeError(
            "Modelo de embedding alternativo exige o extra 'embeddings'. "
            'Instale com: python -m pip install -e ".[embeddings]"'
        ) from exc


def _obter_colecao(
    cliente,
    nome: str,
    modelo_embedding: str,
    embedding_function,
    metadata: dict,
):
    funcao = embedding_function
    if funcao is None:
        funcao = criar_funcao_embedding(modelo_embedding)
    metadata = {**metadata, "modelo_embedding": modelo_embedding}
    argumentos = {"name": nome, "metadata": metadata}
    if funcao is not None:
        argumentos["embedding_function"] = funcao
    colecao = cliente.get_or_create_collection(**argumentos)
    metadata_existente = getattr(colecao, "metadata", None) or {}
    modelo_existente = metadata_existente.get(
        "modelo_embedding", MODELO_EMBEDDING_PADRAO
    )
    if modelo_existente != modelo_embedding:
        raise ValueError(
            f"Coleção {nome!r} usa embedding {modelo_existente!r}, não "
            f"{modelo_embedding!r}. Use outro --chroma-path."
        )
    return colecao


def _metadata(decisao: Decisao) -> dict[str, str | int | bool]:
    metadata: dict[str, str | int | bool] = {
        "cd_acordao": decisao.cd_acordao,
        "cd_foro": decisao.cd_foro,
        "processo": decisao.processo,
        "inteiro_teor_url": decisao.inteiro_teor_url,
        "tipo_registro": "ementa",
    }
    opcionais = {
        "classe": decisao.classe,
        "assunto": decisao.assunto,
        "relator": decisao.relator,
        "comarca": decisao.comarca,
        "orgao_julgador": decisao.orgao_julgador,
        "data_julgamento": decisao.data_julgamento,
        "data_publicacao": decisao.data_publicacao,
    }
    metadata.update({chave: valor for chave, valor in opcionais.items() if valor})
    if decisao.data_julgamento:
        metadata["data_julgamento_ord"] = _data_ord(decisao.data_julgamento)
    if decisao.data_publicacao:
        metadata["data_publicacao_ord"] = _data_ord(decisao.data_publicacao)
    if decisao.ocorrencias is not None:
        metadata["ocorrencias"] = decisao.ocorrencias
    return metadata


def _metadata_chunk(
    chunk: ChunkJuridico,
    resultado: ResultadoProcessamento,
    decisao: Decisao,
) -> dict[str, str | int | bool]:
    metadata = _metadata(decisao)
    metadata.update(
        {
            "tipo_registro": "inteiro_teor",
            "pagina": chunk.pagina,
            "indice_chunk": chunk.indice,
            "sha256": resultado.sha256,
            "arquivo": Path(resultado.caminho_local).name,
            "citacao": (
                f"Processo {decisao.processo}, ac\u00f3rd\u00e3o "
                f"{decisao.cd_acordao}, p. {chunk.pagina}"
            ),
        }
    )
    return metadata


def _data_ord(valor: str) -> int:
    try:
        return int(datetime.strptime(valor, "%d/%m/%Y").strftime("%Y%m%d"))
    except ValueError as exc:
        raise ValueError(f"Data devolvida pelo TJSP é inválida: {valor!r}.") from exc
