from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from requests import RequestException

from .assisted_research import (
    ErroPesquisaAssistida,
    LimiteCustoPesquisa,
    PesquisaAssistidaTJSP,
)
from .client import TRIBUNAIS_CONFIG, TJSPClient
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
from .rag import PacoteContextoIA, PreparadorContextoIA, ProvedorIA
from .search import BuscaHibrida
from .settings import Settings
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
    tribunal: str = Field(default="todos", max_length=20)


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


def criar_app(
    *,
    configuracao: ConfiguracaoAPI | None = None,
    repositorio: RepositorioSQLite | None = None,
    repositorio_chunks: RepositorioChunksChroma | None = None,
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
    if busca is None:
        repositorio_chunks = repositorio_chunks or RepositorioChunksChroma(
            config.chroma_path
        )
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
        title="TJSP Jurisprudência API",
        version="0.1.0",
        description="API para pesquisa jurisprudencial no TJSP e RAG jurídico com Maritaca AI.",
    )
    app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")

    @app.get("/", include_in_schema=False)
    def inicio() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/saude", tags=["sistema"])
    def saude() -> dict:
        contagens = sqlite.contagens_processamento()
        tesseract_disponivel = bool(shutil.which("tesseract"))

        sqlite_ok = True
        try:
            with sqlite._conectar() as conn:
                modo_journal = str(
                    conn.execute("PRAGMA journal_mode").fetchone()[0]
                ).lower()
        except Exception:
            sqlite_ok = False
            modo_journal = "indisponivel"

        chroma_ok = True
        total_chunks = 0
        if repositorio_chunks is not None:
            try:
                total_chunks = repositorio_chunks.colecao.count()
            except Exception:
                chroma_ok = False

        chave_maritaca = bool(os.environ.get("MARITACA_API_KEY", "").strip())
        status_geral = "ok" if (sqlite_ok and chroma_ok) else "atencao"

        return {
            "status": status_geral,
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
            "diagnosticos": {
                "sqlite": {
                    "status": "ok" if sqlite_ok else "erro",
                    "caminho": str(config.sqlite_path),
                    "journal_mode": modo_journal,
                    "contagens": contagens,
                },
                "chroma": {
                    "status": "ok" if chroma_ok else "erro",
                    "caminho": str(config.chroma_path),
                    "total_chunks": total_chunks,
                },
                "maritaca": {
                    "configurada": chave_maritaca,
                    "modelo": os.environ.get("MARITACA_MODEL", "sabia-4"),
                },
                "tesseract_ocr": {
                    "disponivel": tesseract_disponivel,
                    "habilitado": config.habilitar_ocr,
                },
            },
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
                tribunal=requisicao.tribunal,
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
                detail=f"Falha ao consultar o tribunal ({requisicao.tribunal.upper()}): {exc}",
            ) from exc

    @app.get("/tribunais", tags=["tribunais"])
    def listar_tribunais() -> list[dict]:
        return [
            {
                "codigo": codigo,
                "sigla": info["sigla"],
                "nome": info["nome"],
                "uf": info["uf"],
                "ativo": True,
            }
            for codigo, info in TRIBUNAIS_CONFIG.items()
        ]

    @app.post(
        "/tjsp/pesquisa-assistida/stream",
        tags=["inteligencia-artificial", "coleta-tjsp"],
    )
    def pesquisar_tjsp_com_ia_stream(requisicao: RequisicaoPesquisaAssistida):
        limite = requisicao.max_custo_brl or config.max_custo_pesquisa_assistida_brl
        if limite > config.max_custo_pesquisa_assistida_brl:
            raise HTTPException(
                status_code=422,
                detail=(
                    "max_custo_brl excede o limite da pesquisa assistida "
                    f"({config.max_custo_pesquisa_assistida_brl})."
                ),
            )

        def gerador_eventos():
            try:
                for evento in pesquisa_com_ia.pesquisar_stream(
                    requisicao.pergunta,
                    contexto_caso=requisicao.contexto_caso,
                    modelo=requisicao.modelo,
                    max_custo_brl=limite,
                    tribunal=requisicao.tribunal,
                ):
                    yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"
            except Exception as exc:
                erro_payload = json.dumps(
                    {"tipo": "erro", "erro": str(exc)},
                    ensure_ascii=False,
                )
                yield f"data: {erro_payload}\n\n"

        return StreamingResponse(
            gerador_eventos(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

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

    @app.post("/tjsp/gerar-minuta", tags=["tjsp"])
    def gerar_minuta(requisicao: RequisicaoMinuta) -> dict:
        tema = requisicao.tema or requisicao.pergunta
        acordaos = requisicao.acordaos_selecionados
        instrucao = requisicao.instrucao.strip()

        resumo_acordaos = []
        for a in acordaos:
            proc = a.get("processo") or f"Acórdão {a.get('cd_acordao', '')}"
            rel = a.get("relator") or "Relator não informado"
            orgao = a.get("orgao_julgador") or "TJSP"
            dt = a.get("data_julgamento") or ""
            ementa = a.get("ementa") or ""
            arg = a.get("argumento") or a.get("aderencia_fatica") or ""
            resumo_acordaos.append(
                f"- Processo: {proc} | Órgão: {orgao} | Relator: {rel} | Julgamento: {dt}\n"
                f"  Aplicação: {arg}\n"
                f"  Ementa: {ementa[:400]}"
            )
        texto_precedentes = "\n\n".join(resumo_acordaos)

        chave = os.getenv("MARITACA_API_KEY")
        if chave:
            try:
                provedor = criar_provedor(None, 2000)
                prompt_sistema = (
                    "Você é um especialista em redação de peças processuais e teses jurídicas para o Tribunal de Justiça de São Paulo (TJSP).\n"
                    "Redija uma fundamentação jurídica formal, assertiva e bem estruturada para inclusão direta em petição.\n"
                    "Estrutura recomendada:\n"
                    "# EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO...\n\n"
                    "## I. DOS FATOS RELEVANTES E DO CONTEXTO\n"
                    "## II. DA JURISPRUDÊNCIA FIRME DO TJSP (PRECEDENTES APLICÁVEIS)\n"
                    "## III. DA FUNDAMENTAÇÃO E APLICAÇÃO AO CASO CONCRETO\n"
                    "## IV. DOS PEDIDOS E REQUERIMENTOS\n\n"
                    f"Tema: {tema}\n"
                    f"Fatos / Consulta: {requisicao.pergunta}\n"
                    f"Detalhes do caso: {requisicao.contexto_caso}\n\n"
                    f"Precedentes do TJSP Selecionados:\n{texto_precedentes}\n\n"
                )
                if instrucao:
                    prompt_sistema += f"\nInstruções de Ajuste do Advogado: {instrucao}\n"

                pacote = PacoteContextoIA(
                    instrucoes_sistema=prompt_sistema,
                    mensagem_usuario=f"Redija a minuta de fundamentação jurídica com base nos acórdãos: {tema}",
                )
                resposta_ia = provedor.responder(pacote)
                return {
                    "minuta": resposta_ia.texto,
                    "tema": tema,
                    "acordaos_utilizados": len(acordaos),
                }
            except Exception:
                pass

        # Fallback local estruturado
        linhas = [
            f"# MINUTA DE FUNDAMENTAÇÃO JURÍDICA — {tema.upper()}",
            "",
            "## I. DO CONTEXTO FÁTICO",
            requisicao.contexto_caso or requisicao.pergunta,
            "",
            "## II. DA JURISPRUDÊNCIA PACÍFICA DO TRIBUNAL DE JUSTIÇA DE SÃO PAULO",
            "A pretensão formulada encontra integral acolhimento na iterativa jurisprudência desta Egrégia Corte bandeirante:",
            "",
        ]
        for idx, a in enumerate(acordaos, 1):
            proc = a.get("processo") or f"Acórdão nº {a.get('cd_acordao', '')}"
            rel = a.get("relator") or "Relator designado"
            orgao = a.get("orgao_julgador") or "Tribunal de Justiça de São Paulo"
            dt = f", j. em {a.get('data_julgamento')}" if a.get("data_julgamento") else ""
            ementa = a.get("ementa", "").strip()
            arg = a.get("argumento") or a.get("aderencia_fatica") or ""

            linhas.append(f"### {idx}. {proc} — {orgao}")
            if rel:
                linhas.append(f"**Relator(a):** {rel}{dt}")
            if arg:
                linhas.append(f"**Tese Aplicável:** {arg}")
            if ementa:
                linhas.append(f"\n> *\"{ementa}\"*\n")

        linhas.extend([
            "## III. DA SUBSUNÇÃO FÁTICA E DO DIREITO",
            f"Como se extrai dos precedentes colacionados, a jurisprudência do TJSP é uníssona em acolher o pleito ora formulado quanto ao tema '{tema}', sendo manifesto o direito da parte requerente.",
            "",
            "## IV. DOS PEDIDOS",
            "Ante o exposto, requer-se o acolhimento integral da tese com base na iterativa jurisprudência desta Corte.",
        ])

        if instrucao:
            linhas.extend(["", f"*(Ajuste solicitado pelo advogado: {instrucao})*"])

        return {
            "minuta": "\n".join(linhas),
            "tema": tema,
            "acordaos_utilizados": len(acordaos),
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
