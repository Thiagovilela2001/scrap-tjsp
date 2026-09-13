from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .settings import Settings


@dataclass(slots=True, frozen=True)
class ConfiguracaoAPI:
    sqlite_path: Path = Path("data/tjsp.sqlite3")
    chroma_path: Path = Path("data/chroma")
    max_custo_brl: float = 0.10
    max_output_tokens: int = 2_000
    diretorio_pdfs: Path = Path("data/pdfs")
    intervalo_tjsp: float = 2.0
    max_paginas_tjsp: int = 1
    max_importacao_pdfs: int = 5
    max_mb_pdf: int = 50
    habilitar_ocr: bool = True
    max_custo_pesquisa_assistida_brl: float = 0.20
    max_custo_analise_documental_brl: float = 0.20

    def __post_init__(self) -> None:
        if self.max_custo_brl <= 0:
            raise ValueError("TJSP_API_MAX_CUSTO_BRL deve ser positivo.")
        if self.max_output_tokens < 1:
            raise ValueError("TJSP_API_MAX_OUTPUT_TOKENS deve ser pelo menos 1.")
        if self.intervalo_tjsp < 1:
            raise ValueError("TJSP_API_INTERVALO_TJSP deve ser pelo menos 1 segundo.")
        if self.max_paginas_tjsp < 1 or self.max_importacao_pdfs < 1:
            raise ValueError("Limites de coleta TJSP devem ser positivos.")
        if self.max_mb_pdf < 1:
            raise ValueError("TJSP_API_MAX_MB_PDF deve ser positivo.")
        if self.max_custo_pesquisa_assistida_brl <= 0:
            raise ValueError("TJSP_API_MAX_CUSTO_PESQUISA_BRL deve ser positivo.")
        if self.max_custo_analise_documental_brl <= 0:
            raise ValueError("TJSP_API_MAX_CUSTO_ANALISE_BRL deve ser positivo.")

    @classmethod
    def do_ambiente(cls) -> ConfiguracaoAPI:
        s = Settings.carregar()
        return cls(
            sqlite_path=s.sqlite_path,
            chroma_path=s.chroma_path,
            max_custo_brl=s.max_custo_brl,
            max_output_tokens=s.max_output_tokens,
            diretorio_pdfs=s.diretorio_pdfs,
            intervalo_tjsp=s.intervalo_tjsp,
            max_paginas_tjsp=s.max_paginas_tjsp,
            max_importacao_pdfs=s.max_importacao_pdfs,
            max_mb_pdf=s.max_mb_pdf,
            habilitar_ocr=s.habilitar_ocr,
            max_custo_pesquisa_assistida_brl=s.max_custo_pesquisa_assistida_brl,
            max_custo_analise_documental_brl=s.max_custo_analise_documental_brl,
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


class RequisicaoPesquisaTJSP(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pesquisa: str = Field(min_length=1, max_length=120)
    ementa: str = Field(default="", max_length=120)
    classe: str = Field(default="", max_length=100)
    assunto: str = Field(default="", max_length=100)
    comarca: str = Field(default="", max_length=100)
    orgao_julgador: str = Field(default="", max_length=100)
    inicio: str = Field(default="", max_length=10)
    fim: str = Field(default="", max_length=10)
    origem: Literal["segundo_grau", "colegio_recursal"] = "segundo_grau"
    tipo: Literal["acordao", "homologacao", "monocratica"] = "acordao"
    sinonimos: bool = True
    paginas: int = Field(default=1, ge=1)


class RequisicaoImportacaoTJSP(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consulta_id: int = Field(ge=1)
    cd_acordaos: list[str] = Field(min_length=1, max_length=20)


class RequisicaoPesquisaAssistida(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pergunta: str = Field(min_length=1, max_length=2_000)
    contexto_caso: str = Field(default="", max_length=8_000)
    modelo: str | None = Field(default=None, min_length=1, max_length=100)
    max_custo_brl: float | None = Field(default=None, gt=0)
    tribunal: str = Field(default="todos", max_length=1_000)


class RequisicaoAnaliseDocumental(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pergunta: str = Field(min_length=5, max_length=2_000)
    contexto_caso: str = Field(default="", max_length=8_000)
    cd_acordaos: list[str] = Field(min_length=1, max_length=5)
    modelo: str | None = Field(default=None, min_length=1, max_length=100)
    max_custo_brl: float | None = Field(default=None, gt=0)


class RequisicaoMinuta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tema: str = Field(default="", max_length=2_000)
    pergunta: str = Field(min_length=3, max_length=4_000)
    contexto_caso: str = Field(default="", max_length=8_000)
    acordaos_selecionados: list[dict] = Field(default_factory=list)
    instrucao: str = Field(default="", max_length=2_000)
    historico_chat: list[dict] = Field(default_factory=list)


def validar_limites(
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
