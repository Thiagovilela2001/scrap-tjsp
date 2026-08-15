from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from requests import RequestException

from .assisted_research import (
    ErroPesquisaAssistida,
    LimiteCustoPesquisa,
    PesquisaAssistidaTJSP,
)
from .client import TJSPClient
from .cost import PrecosTokens, estimar_custo_maximo, resumir_custo
from .document_analysis import (
    AnaliseDocumentalTJSP,
    ErroAnaliseDocumental,
    LimiteCustoAnalise,
)
from .downloader import PDFDownloader
from .ingestion import ServicoColetaTJSP
from .maritaca import ErroMaritaca, ProvedorMaritaca
from .models import Consulta
from .processor import ProcessadorPDF
from .rag import PreparadorContextoIA, ProvedorIA
from .search import BuscaHibrida
from .storage import RepositorioSQLite
from .vector_store import RepositorioChroma, RepositorioChunksChroma


class ProvedorConfigurado(ProvedorIA, Protocol):
    modelo: str


ProvedorFactory = Callable[[str | None, int], ProvedorConfigurado]
WEB_DIR = Path(__file__).with_name("web")


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
        return cls(
            sqlite_path=Path(os.environ.get("TJSP_SQLITE_PATH", "data/tjsp.sqlite3")),
            chroma_path=Path(os.environ.get("TJSP_CHROMA_PATH", "data/chroma")),
            max_custo_brl=_float_ambiente("TJSP_API_MAX_CUSTO_BRL", 0.10),
            max_output_tokens=_int_ambiente("TJSP_API_MAX_OUTPUT_TOKENS", 2_000),
            diretorio_pdfs=Path(os.environ.get("TJSP_DIRETORIO_PDFS", "data/pdfs")),
            intervalo_tjsp=_float_ambiente("TJSP_API_INTERVALO_TJSP", 2.0),
            max_paginas_tjsp=_int_ambiente("TJSP_API_MAX_PAGINAS_TJSP", 1),
            max_importacao_pdfs=_int_ambiente("TJSP_API_MAX_IMPORTACAO_PDFS", 5),
            max_mb_pdf=_int_ambiente("TJSP_API_MAX_MB_PDF", 50),
            habilitar_ocr=_bool_ambiente("TJSP_API_HABILITAR_OCR", True),
            max_custo_pesquisa_assistida_brl=_float_ambiente(
                "TJSP_API_MAX_CUSTO_PESQUISA_BRL",
                0.20,
            ),
            max_custo_analise_documental_brl=_float_ambiente(
                "TJSP_API_MAX_CUSTO_ANALISE_BRL",
                0.20,
            ),
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
    model_config = ConfigDict(extra="forbid")

    pergunta: str = Field(min_length=5, max_length=2_000)
    contexto_caso: str = Field(default="", max_length=8_000)
    modelo: str | None = Field(default=None, min_length=1, max_length=100)
    max_custo_brl: float | None = Field(default=None, gt=0)


class RequisicaoAnaliseDocumental(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pergunta: str = Field(min_length=5, max_length=2_000)
    contexto_caso: str = Field(default="", max_length=8_000)
    cd_acordaos: list[str] = Field(min_length=1, max_length=5)
    modelo: str | None = Field(default=None, min_length=1, max_length=100)
    max_custo_brl: float | None = Field(default=None, gt=0)


def criar_app(
    *,
    configuracao: ConfiguracaoAPI | None = None,
    repositorio: RepositorioSQLite | None = None,
    busca: BuscaHibrida | None = None,
    provedor_factory: ProvedorFactory | None = None,
    servico_tjsp: ServicoColetaTJSP | None = None,
    pesquisa_assistida: PesquisaAssistidaTJSP | None = None,
    analise_documental: AnaliseDocumentalTJSP | None = None,
) -> FastAPI:
    load_dotenv()
    config = configuracao or ConfiguracaoAPI.do_ambiente()
    sqlite = repositorio or RepositorioSQLite(config.sqlite_path)
    sqlite.inicializar()
    repositorio_chunks = None
    if busca is None:
        repositorio_chunks = RepositorioChunksChroma(config.chroma_path)
        busca_hibrida = BuscaHibrida(sqlite, repositorio_chunks)
    else:
        busca_hibrida = busca
    if servico_tjsp is None:
        repositorio_chunks = repositorio_chunks or RepositorioChunksChroma(
            config.chroma_path
        )
        cliente_tjsp = TJSPClient(intervalo=config.intervalo_tjsp)
        servico_coleta = ServicoColetaTJSP(
            sqlite,
            cliente_tjsp,
            PDFDownloader(
                cliente_tjsp,
                diretorio=config.diretorio_pdfs,
                limite_bytes=config.max_mb_pdf * 1024 * 1024,
            ),
            ProcessadorPDF(habilitar_ocr=config.habilitar_ocr),
            RepositorioChroma(config.chroma_path),
            repositorio_chunks,
            max_paginas=config.max_paginas_tjsp,
            max_pdfs=config.max_importacao_pdfs,
        )
    else:
        servico_coleta = servico_tjsp
    criar_provedor = provedor_factory or _criar_provedor_maritaca
    pesquisa_com_ia = pesquisa_assistida or PesquisaAssistidaTJSP(
        sqlite,
        servico_coleta,
        criar_provedor,
    )
    analise_de_documentos = analise_documental or AnaliseDocumentalTJSP(
        sqlite,
        busca_hibrida,
        criar_provedor,
    )
    preparador = PreparadorContextoIA(busca_hibrida)
    precos = PrecosTokens()

    app = FastAPI(
        title="Scraping TJSP API",
        version="0.2.0",
        description="Busca híbrida e respostas rastreáveis sobre jurisprudência do TJSP.",
    )
    app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")

    @app.get("/", include_in_schema=False)
    def inicio() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/saude", tags=["sistema"])
    def saude() -> dict:
        contagens = sqlite.contagens_processamento()
        return {
            "status": "ok",
            "provedor_ia": "maritaca",
            "max_custo_brl": config.max_custo_brl,
            "max_output_tokens": config.max_output_tokens,
            "chunks_indexados": contagens["chunks_documento"],
            "max_paginas_tjsp": config.max_paginas_tjsp,
            "max_importacao_pdfs": config.max_importacao_pdfs,
            "intervalo_tjsp_segundos": config.intervalo_tjsp,
            "max_custo_pesquisa_assistida_brl": (
                config.max_custo_pesquisa_assistida_brl
            ),
            "max_custo_analise_documental_brl": (
                config.max_custo_analise_documental_brl
            ),
        }

    @app.get("/documentos/{cd_acordao}", tags=["documentos"])
    def abrir_documento(cd_acordao: str) -> FileResponse:
        try:
            documento = sqlite.obter_documento(cd_acordao)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        caminho = Path(documento["caminho_local"] or "").resolve()
        diretorio_permitido = config.diretorio_pdfs.resolve()
        if not caminho.is_relative_to(diretorio_permitido):
            raise HTTPException(
                status_code=403,
                detail="PDF registrado fora do diretório permitido.",
            )
        if not caminho.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"Arquivo local do acórdão {cd_acordao} não encontrado.",
            )
        return FileResponse(
            caminho,
            media_type=documento["mime_type"] or "application/pdf",
            filename=caminho.name,
            content_disposition_type="inline",
        )

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

    @app.post("/tjsp/pesquisar", tags=["coleta-tjsp"])
    def pesquisar_tjsp(requisicao: RequisicaoPesquisaTJSP) -> dict:
        consulta = Consulta(
            pesquisa=requisicao.pesquisa.strip(),
            ementa=requisicao.ementa.strip(),
            classe=requisicao.classe.strip(),
            assunto=requisicao.assunto.strip(),
            comarca=requisicao.comarca.strip(),
            orgao_julgador=requisicao.orgao_julgador.strip(),
            data_julgamento_inicio=requisicao.inicio,
            data_julgamento_fim=requisicao.fim,
            origem=requisicao.origem,
            tipo_decisao=requisicao.tipo,
            pesquisar_sinonimos=requisicao.sinonimos,
        )
        try:
            return servico_coleta.pesquisar(consulta, paginas=requisicao.paginas)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Falha ao consultar o TJSP: {exc}",
            ) from exc

    @app.post("/tjsp/importar", tags=["coleta-tjsp"])
    def importar_tjsp(requisicao: RequisicaoImportacaoTJSP) -> dict:
        try:
            return servico_coleta.importar(
                requisicao.consulta_id,
                requisicao.cd_acordaos,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post(
        "/tjsp/pesquisa-assistida",
        tags=["inteligencia-artificial", "coleta-tjsp"],
    )
    def pesquisar_tjsp_com_ia(requisicao: RequisicaoPesquisaAssistida) -> dict:
        limite = requisicao.max_custo_brl or config.max_custo_pesquisa_assistida_brl
        if limite > config.max_custo_pesquisa_assistida_brl:
            raise HTTPException(
                status_code=422,
                detail=(
                    "max_custo_brl excede o limite da pesquisa assistida "
                    f"({config.max_custo_pesquisa_assistida_brl})."
                ),
            )
        try:
            return pesquisa_com_ia.pesquisar(
                requisicao.pergunta,
                contexto_caso=requisicao.contexto_caso,
                modelo=requisicao.modelo,
                max_custo_brl=limite,
            )
        except LimiteCustoPesquisa as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "erro": str(exc),
                    "estimativa_maxima_brl": round(exc.estimativa, 6),
                    "limite_brl": exc.limite,
                },
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ErroMaritaca as exc:
            status = 503 if "MARITACA_API_KEY" in str(exc) else 502
            raise HTTPException(status_code=status, detail=str(exc)) from exc
        except ErroPesquisaAssistida as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Falha ao consultar o TJSP: {exc}",
            ) from exc

    @app.post(
        "/tjsp/analisar-documentos",
        tags=["inteligencia-artificial", "documentos"],
    )
    def analisar_documentos(requisicao: RequisicaoAnaliseDocumental) -> dict:
        limite = requisicao.max_custo_brl or config.max_custo_analise_documental_brl
        if limite > config.max_custo_analise_documental_brl:
            raise HTTPException(
                status_code=422,
                detail=(
                    "max_custo_brl excede o limite da análise documental "
                    f"({config.max_custo_analise_documental_brl})."
                ),
            )
        try:
            return analise_de_documentos.analisar(
                requisicao.pergunta,
                requisicao.cd_acordaos,
                contexto_caso=requisicao.contexto_caso,
                modelo=requisicao.modelo,
                max_custo_brl=limite,
            )
        except LimiteCustoAnalise as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "erro": str(exc),
                    "estimativa_maxima_brl": round(exc.estimativa, 6),
                    "limite_brl": exc.limite,
                },
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ErroMaritaca as exc:
            status = 503 if "MARITACA_API_KEY" in str(exc) else 502
            raise HTTPException(status_code=status, detail=str(exc)) from exc
        except ErroAnaliseDocumental as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

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


def _bool_ambiente(nome: str, padrao: bool) -> bool:
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    normalizado = valor.strip().casefold()
    if normalizado in {"1", "true", "sim", "yes", "on"}:
        return True
    if normalizado in {"0", "false", "nao", "não", "no", "off"}:
        return False
    raise ValueError(f"{nome} deve ser booleano.")
