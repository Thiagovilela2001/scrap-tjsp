from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from requests import RequestException

from .api_schemas import (
    ConfiguracaoAPI,
    RequisicaoBusca,
    RequisicaoImportacaoTJSP,
    RequisicaoPesquisaTJSP,
)
from .client import TRIBUNAIS_CONFIG, TJSPClient
from .downloader import PDFDownloader
from .ingestion import ServicoColetaTJSP
from .models import Consulta
from .search import BuscaHibrida
from .storage import RepositorioSQLite


def criar_router_juris(
    *,
    sqlite: RepositorioSQLite,
    busca_hibrida: BuscaHibrida,
    servico_coleta: ServicoColetaTJSP,
    cliente_tjsp: TJSPClient,
    config: ConfiguracaoAPI,
) -> APIRouter:
    router = APIRouter()

    @router.get("/documentos/{cd_acordao}", tags=["documentos"])
    def abrir_documento(cd_acordao: str) -> FileResponse:
        try:
            documento = sqlite.obter_documento(cd_acordao)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except LookupError:
            decisao = sqlite.obter_decisao(cd_acordao)
            if decisao and decisao.inteiro_teor_url:
                try:
                    downloader = PDFDownloader(
                        cliente_tjsp,
                        diretorio=config.diretorio_pdfs,
                        limite_bytes=config.max_mb_pdf * 1024 * 1024,
                    )
                    baixado = downloader.baixar(decisao)
                    sqlite.registrar_documento(baixado)
                    documento = sqlite.obter_documento(cd_acordao)
                except Exception as exc:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Não foi possível obter o inteiro teor do documento: {exc}",
                    ) from exc
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"Arquivo local do acórdão {cd_acordao} não encontrado.",
                )
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

    @router.post("/buscar", tags=["jurisprudencia"])
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

    @router.post("/tjsp/pesquisar", tags=["coleta-tjsp"])
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

    @router.post("/tjsp/importar", tags=["coleta-tjsp"])
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

    @router.get("/tribunais", tags=["tribunais"])
    def listar_tribunais() -> list[dict]:
        return [
            {
                "codigo": codigo,
                "sigla": info["sigla"],
                "nome": info["nome"],
                "uf": info["uf"],
                "adaptador": info["adaptador"],
                "ativo": info["ativo"],
                "motivo_inativo": info.get("motivo_inativo", ""),
            }
            for codigo, info in TRIBUNAIS_CONFIG.items()
        ]

    return router
