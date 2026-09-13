from __future__ import annotations

import json
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from requests import RequestException

from .api_schemas import (
    ConfiguracaoAPI,
    RequisicaoAnaliseDocumental,
    RequisicaoMinuta,
    RequisicaoPergunta,
    RequisicaoPesquisaAssistida,
    validar_limites,
)
from .assisted_research import (
    ErroPesquisaAssistida,
    LimiteCustoPesquisa,
    PesquisaAssistidaTJSP,
)
from .cost import PrecosTokens, estimar_custo_maximo, resumir_custo
from .document_analysis import (
    AnaliseDocumentalTJSP,
    ErroAnaliseDocumental,
    LimiteCustoAnalise,
)
from .maritaca import ErroMaritaca
from .rag import PreparadorContextoIA
from .storage import RepositorioSQLite


def criar_router_ia(
    *,
    sqlite: RepositorioSQLite,
    pesquisa_com_ia: PesquisaAssistidaTJSP,
    analise_de_documentos: AnaliseDocumentalTJSP,
    preparador: PreparadorContextoIA,
    precos: PrecosTokens,
    criar_provedor: Callable,
    config: ConfiguracaoAPI,
) -> APIRouter:
    router = APIRouter()

    @router.post(
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

    @router.post(
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

    # Aliases agnósticos de tribunal
    router.post(
        "/pesquisa-assistida",
        tags=["inteligencia-artificial"],
    )(pesquisar_tjsp_com_ia)
    router.post(
        "/pesquisa-assistida/stream",
        tags=["inteligencia-artificial"],
    )(pesquisar_tjsp_com_ia_stream)

    @router.post(
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

    @router.post(
        "/tjsp/analisar-documentos/stream",
        tags=["inteligencia-artificial", "documentos"],
    )
    def analisar_documentos_stream(requisicao: RequisicaoAnaliseDocumental):
        limite = (
            requisicao.max_custo_brl
            or config.max_custo_analise_documental_brl
        )
        if limite > config.max_custo_analise_documental_brl:
            raise HTTPException(
                status_code=422,
                detail=(
                    "max_custo_brl excede o limite da análise documental "
                    f"({config.max_custo_analise_documental_brl})."
                ),
            )

        def gerador_eventos():
            try:
                for evento in analise_de_documentos.analisar_stream(
                    requisicao.pergunta,
                    requisicao.cd_acordaos,
                    contexto_caso=requisicao.contexto_caso,
                    modelo=requisicao.modelo,
                    max_custo_brl=limite,
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


    @router.post("/tjsp/gerar-minuta", tags=["tjsp"])
    def gerar_minuta(requisicao: RequisicaoMinuta) -> dict:
        from .minuta import gerar_minuta_juridica

        return gerar_minuta_juridica(requisicao, criar_provedor)

    @router.post("/perguntar", tags=["inteligencia-artificial"])
    def perguntar(requisicao: RequisicaoPergunta) -> dict:
        pergunta = requisicao.pergunta.strip()
        if not pergunta:
            raise HTTPException(status_code=422, detail="Pergunta não pode ser vazia.")
        validar_limites(requisicao, config)
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

    @router.get("/auditorias", tags=["auditoria"])
    def listar_auditorias(
        limite: int = Query(default=20, ge=1, le=100),
    ) -> list[dict]:
        return sqlite.listar_execucoes_ia(limite=limite)

    @router.get("/auditorias/{execucao_id}", tags=["auditoria"])
    def obter_auditoria(execucao_id: int) -> dict:
        try:
            return sqlite.obter_execucao_ia(execucao_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router
