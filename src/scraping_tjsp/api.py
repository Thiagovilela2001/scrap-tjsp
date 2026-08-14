from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from .cost import PrecosTokens, estimar_custo_maximo, resumir_custo
from .maritaca import ErroMaritaca, ProvedorMaritaca
from .rag import PreparadorContextoIA, ProvedorIA
from .search import BuscaHibrida
from .storage import RepositorioSQLite
from .vector_store import RepositorioChunksChroma


class ProvedorConfigurado(ProvedorIA, Protocol):
    modelo: str


ProvedorFactory = Callable[[str | None, int], ProvedorConfigurado]


@dataclass(slots=True, frozen=True)
class ConfiguracaoAPI:
    sqlite_path: Path = Path("data/tjsp.sqlite3")
    chroma_path: Path = Path("data/chroma")
    max_custo_brl: float = 0.10
    max_output_tokens: int = 2_000

    def __post_init__(self) -> None:
        if self.max_custo_brl <= 0:
            raise ValueError("TJSP_API_MAX_CUSTO_BRL deve ser positivo.")
        if self.max_output_tokens < 1:
            raise ValueError("TJSP_API_MAX_OUTPUT_TOKENS deve ser pelo menos 1.")

    @classmethod
    def do_ambiente(cls) -> ConfiguracaoAPI:
        return cls(
            sqlite_path=Path(os.environ.get("TJSP_SQLITE_PATH", "data/tjsp.sqlite3")),
            chroma_path=Path(os.environ.get("TJSP_CHROMA_PATH", "data/chroma")),
            max_custo_brl=_float_ambiente("TJSP_API_MAX_CUSTO_BRL", 0.10),
            max_output_tokens=_int_ambiente("TJSP_API_MAX_OUTPUT_TOKENS", 2_000),
        )


class FiltrosBusca(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cd_acordao: str | None = None
    processo: str | None = None
    classe: str | None = None
    assunto: str | None = None
    orgao_julgador: str | None = None
    pagina: int | None = Field(default=None, ge=1)

    def como_dict(self) -> dict[str, str | int]:
        return {
            chave: valor
            for chave, valor in self.model_dump(exclude_none=True).items()
            if valor != ""
        }


class RequisicaoBusca(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pergunta: str = Field(min_length=1, max_length=2_000)
    limite: int = Field(default=10, ge=1, le=50)
    filtros: FiltrosBusca = Field(default_factory=FiltrosBusca)


class RequisicaoPergunta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pergunta: str = Field(min_length=1, max_length=2_000)
    limite_fontes: int = Field(default=6, ge=1, le=20)
    max_caracteres: int = Field(default=12_000, ge=500, le=50_000)
    max_output_tokens: int = Field(default=800, ge=1)
    max_custo_brl: float | None = Field(default=None, gt=0)
    modelo: str | None = Field(default=None, min_length=1, max_length=100)
    filtros: FiltrosBusca = Field(default_factory=FiltrosBusca)


def criar_app(
    *,
    configuracao: ConfiguracaoAPI | None = None,
    repositorio: RepositorioSQLite | None = None,
    busca: BuscaHibrida | None = None,
    provedor_factory: ProvedorFactory | None = None,
) -> FastAPI:
    load_dotenv()
    config = configuracao or ConfiguracaoAPI.do_ambiente()
    sqlite = repositorio or RepositorioSQLite(config.sqlite_path)
    sqlite.inicializar()
    busca_hibrida = busca or BuscaHibrida(
        sqlite,
        RepositorioChunksChroma(config.chroma_path),
    )
    criar_provedor = provedor_factory or _criar_provedor_maritaca
    preparador = PreparadorContextoIA(busca_hibrida)
    precos = PrecosTokens()

    app = FastAPI(
        title="Scraping TJSP API",
        version="0.2.0",
        description="Busca híbrida e respostas rastreáveis sobre jurisprudência do TJSP.",
    )

    @app.get("/", include_in_schema=False)
    def inicio() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    @app.get("/saude", tags=["sistema"])
    def saude() -> dict:
        return {
            "status": "ok",
            "provedor_ia": "maritaca",
            "max_custo_brl": config.max_custo_brl,
            "max_output_tokens": config.max_output_tokens,
        }

    @app.post("/buscar", tags=["jurisprudencia"])
    def buscar_jurisprudencia(requisicao: RequisicaoBusca) -> dict:
        pergunta = requisicao.pergunta.strip()
        if not pergunta:
            raise HTTPException(status_code=422, detail="Pergunta não pode ser vazia.")
        try:
            resultados = busca_hibrida.buscar(
                pergunta,
                limite=requisicao.limite,
                filtros=requisicao.filtros.como_dict(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "consulta": pergunta,
            "total": len(resultados),
            "resultados": [resultado.como_dict() for resultado in resultados],
        }

    @app.post("/perguntar", tags=["inteligencia-artificial"])
    def perguntar(requisicao: RequisicaoPergunta) -> dict:
        pergunta = requisicao.pergunta.strip()
        if not pergunta:
            raise HTTPException(status_code=422, detail="Pergunta não pode ser vazia.")
        _validar_limites(requisicao, config)
        try:
            pacote = preparador.preparar(
                pergunta,
                limite_fontes=requisicao.limite_fontes,
                max_caracteres=requisicao.max_caracteres,
                filtros=requisicao.filtros.como_dict(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not pacote.fontes:
            raise HTTPException(
                status_code=422,
                detail="Nenhuma fonte foi encontrada; chamada de IA não realizada.",
            )

        limite_custo = requisicao.max_custo_brl or config.max_custo_brl
        estimativa = estimar_custo_maximo(
            [pacote],
            max_output_tokens=requisicao.max_output_tokens,
            precos=precos,
        )
        if estimativa > limite_custo:
            raise HTTPException(
                status_code=422,
                detail={
                    "erro": "Custo máximo estimado excede o limite da requisição.",
                    "estimativa_maxima_brl": round(estimativa, 6),
                    "limite_brl": limite_custo,
                },
            )

        try:
            provedor = criar_provedor(
                requisicao.modelo,
                requisicao.max_output_tokens,
            )
        except ErroMaritaca as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        configuracao_auditoria = {
            "limite_fontes": requisicao.limite_fontes,
            "max_caracteres": requisicao.max_caracteres,
            "max_output_tokens": requisicao.max_output_tokens,
            "max_custo_brl": limite_custo,
            "estimativa_maxima_brl": round(estimativa, 6),
            "filtros": requisicao.filtros.como_dict(),
        }
        execucao_id = sqlite.iniciar_execucao_ia(
            pacote,
            provedor="maritaca",
            modelo=provedor.modelo,
            configuracao=configuracao_auditoria,
        )
        try:
            resposta = provedor.responder(pacote)
        except ErroMaritaca as exc:
            sqlite.falhar_execucao_ia(
                execucao_id,
                str(exc),
                duracao_ms=exc.duracao_ms,
            )
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        sqlite.concluir_execucao_ia(execucao_id, resposta)
        custo = resumir_custo(
            [resposta],
            precos=precos,
            estimativa_maxima=estimativa,
            limite_brl=limite_custo,
        )
        return {
            "auditoria_id": execucao_id,
            **resposta.como_dict(),
            "fontes": pacote.como_dict()["fontes"],
            "custo": custo,
        }

    @app.get("/auditorias", tags=["auditoria"])
    def listar_auditorias(
        limite: int = Query(default=20, ge=1, le=100),
    ) -> list[dict]:
        return sqlite.listar_execucoes_ia(limite=limite)

    @app.get("/auditorias/{execucao_id}", tags=["auditoria"])
    def obter_auditoria(execucao_id: int) -> dict:
        try:
            return sqlite.obter_execucao_ia(execucao_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app


def _validar_limites(
    requisicao: RequisicaoPergunta,
    config: ConfiguracaoAPI,
) -> None:
    if requisicao.max_output_tokens > config.max_output_tokens:
        raise HTTPException(
            status_code=422,
            detail=(
                "max_output_tokens excede o limite do servidor "
                f"({config.max_output_tokens})."
            ),
        )
    if (
        requisicao.max_custo_brl is not None
        and requisicao.max_custo_brl > config.max_custo_brl
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                f"max_custo_brl excede o limite do servidor ({config.max_custo_brl})."
            ),
        )


def _criar_provedor_maritaca(
    modelo: str | None,
    max_output_tokens: int,
) -> ProvedorMaritaca:
    return ProvedorMaritaca(
        modelo=modelo,
        max_output_tokens=max_output_tokens,
    )


def _float_ambiente(nome: str, padrao: float) -> float:
    valor = os.environ.get(nome)
    try:
        return float(valor) if valor is not None else padrao
    except ValueError as exc:
        raise ValueError(f"{nome} deve ser numérico.") from exc


def _int_ambiente(nome: str, padrao: int) -> int:
    valor = os.environ.get(nome)
    try:
        return int(valor) if valor is not None else padrao
    except ValueError as exc:
        raise ValueError(f"{nome} deve ser inteiro.") from exc
