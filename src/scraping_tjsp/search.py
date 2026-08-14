from __future__ import annotations

from dataclasses import asdict, dataclass

from .storage import RepositorioSQLite
from .vector_store import RepositorioChunksChroma


@dataclass(slots=True, frozen=True)
class ResultadoBuscaHibrida:
    id: str
    texto: str
    metadata: dict
    score_hibrido: float
    origens: tuple[str, ...]
    rank_semantico: int | None = None
    rank_lexical: int | None = None
    distancia_semantica: float | None = None
    score_bm25: float | None = None

    def como_dict(self) -> dict:
        return asdict(self)


class BuscaHibrida:
    def __init__(
        self,
        sqlite: RepositorioSQLite,
        chroma: RepositorioChunksChroma,
        *,
        constante_rrf: int = 60,
        peso_semantico: float = 1.0,
        peso_lexical: float = 1.0,
    ) -> None:
        if constante_rrf < 1:
            raise ValueError("Constante RRF deve ser pelo menos 1.")
        if peso_semantico <= 0 or peso_lexical <= 0:
            raise ValueError("Pesos da busca devem ser positivos.")
        self.sqlite = sqlite
        self.chroma = chroma
        self.constante_rrf = constante_rrf
        self.peso_semantico = peso_semantico
        self.peso_lexical = peso_lexical

    def buscar(
        self,
        texto: str,
        *,
        limite: int = 10,
        candidatos: int | None = None,
        filtros: dict[str, str | int] | None = None,
    ) -> list[ResultadoBuscaHibrida]:
        if not texto.strip():
            raise ValueError("Texto de busca não pode ser vazio.")
        if limite < 1:
            raise ValueError("Limite deve ser pelo menos 1.")
        quantidade_candidatos = candidatos or max(20, limite * 3)
        if quantidade_candidatos < limite:
            raise ValueError("Quantidade de candidatos não pode ser menor que limite.")

        filtros = filtros or {}
        semanticos = self.chroma.buscar(
            texto,
            limite=quantidade_candidatos,
            filtros=_filtros_chroma(filtros),
        )
        lexicais = self.sqlite.buscar_chunks_lexical(
            texto,
            limite=quantidade_candidatos,
            filtros=filtros,
        )
        acumulados: dict[str, dict] = {}
        self._acumular(acumulados, semanticos, "semantica")
        self._acumular(acumulados, lexicais, "lexical")

        ordenados = sorted(
            acumulados.values(),
            key=lambda item: (-item["score_hibrido"], item["id"]),
        )
        return [
            ResultadoBuscaHibrida(
                id=item["id"],
                texto=item["texto"],
                metadata=item["metadata"],
                score_hibrido=item["score_hibrido"],
                origens=tuple(item["origens"]),
                rank_semantico=item.get("rank_semantico"),
                rank_lexical=item.get("rank_lexical"),
                distancia_semantica=item.get("distancia_semantica"),
                score_bm25=item.get("score_bm25"),
            )
            for item in ordenados[:limite]
        ]

    def _acumular(self, acumulados: dict, resultados: list[dict], origem: str) -> None:
        peso = self.peso_semantico if origem == "semantica" else self.peso_lexical
        for rank, resultado in enumerate(resultados, start=1):
            item = acumulados.setdefault(
                resultado["id"],
                {
                    "id": resultado["id"],
                    "texto": resultado["documento"],
                    "metadata": dict(resultado["metadata"]),
                    "score_hibrido": 0.0,
                    "origens": [],
                },
            )
            item["score_hibrido"] += peso / (self.constante_rrf + rank)
            for chave, valor in resultado["metadata"].items():
                item["metadata"].setdefault(chave, valor)
            item["origens"].append(origem)
            if origem == "semantica":
                item["rank_semantico"] = rank
                item["distancia_semantica"] = resultado.get("distancia")
            else:
                item["rank_lexical"] = rank
                item["score_bm25"] = resultado.get("score_bm25")


def _filtros_chroma(filtros: dict[str, str | int]) -> dict | None:
    permitidos = {
        "cd_acordao",
        "processo",
        "classe",
        "assunto",
        "orgao_julgador",
        "pagina",
    }
    invalidos = set(filtros) - permitidos
    if invalidos:
        raise ValueError(f"Filtros não suportados: {sorted(invalidos)}.")
    condicoes = [{chave: valor} for chave, valor in filtros.items()]
    if not condicoes:
        return None
    if len(condicoes) == 1:
        return condicoes[0]
    return {"$and": condicoes}
