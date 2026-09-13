from __future__ import annotations

from typing import TYPE_CHECKING

from .models import Decisao
from .prompts import instrucoes_analise, instrucoes_planejamento
from .rag import FonteContexto, PacoteContextoIA

if TYPE_CHECKING:
    from .assisted_research import ConfiguracaoPesquisaAssistida
    from .cost import PrecosTokens


def pacote_planejamento(
    pergunta: str, contexto: str, tribunal: str = "tjsp"
) -> PacoteContextoIA:
    mensagem = f"Pergunta de pesquisa:\n{pergunta}"
    if contexto:
        mensagem += f"\n\nContexto factual do caso:\n{contexto}"
    return PacoteContextoIA(
        pergunta=pergunta,
        instrucoes_sistema=instrucoes_planejamento(tribunal),
        mensagem_usuario=mensagem,
        fontes=(),
    )


def estimar_maximo_pesquisa(
    pacote_plano: PacoteContextoIA,
    config: ConfiguracaoPesquisaAssistida,
    precos: PrecosTokens,
) -> float:
    from .cost import estimar_custo_maximo

    pacote_maximo = PacoteContextoIA(
        pergunta="estimativa",
        instrucoes_sistema=instrucoes_analise(),
        mensagem_usuario="x" * (config.max_candidatos * config.caracteres_ementa),
        fontes=(),
    )
    return estimar_custo_maximo(
        [pacote_plano],
        max_output_tokens=config.tokens_planejamento,
        precos=precos,
    ) + estimar_custo_maximo(
        [pacote_maximo],
        max_output_tokens=config.tokens_analise,
        precos=precos,
    )


def pacote_analise(
    pergunta: str,
    contexto: str,
    candidatos: list[Decisao],
    config: ConfiguracaoPesquisaAssistida,
    tribunal: str = "tjsp",
) -> PacoteContextoIA:
    fontes = tuple(
        FonteContexto(
            numero=numero,
            id=f"acordao:{decisao.cd_acordao}",
            citacao=f"Processo {decisao.processo}, acórdão {decisao.cd_acordao}",
            url=decisao.inteiro_teor_url,
            texto=decisao.ementa[: config.caracteres_ementa],
            score_hibrido=0.0,
        )
        for numero, decisao in enumerate(candidatos, start=1)
    )
    blocos = [
        f"[Candidato {fonte.numero}]\nID: {candidatos[fonte.numero - 1].cd_acordao}"
        f"\nProcesso: {candidatos[fonte.numero - 1].processo}"
        f"\nClasse: {candidatos[fonte.numero - 1].classe}"
        f"\nAssunto: {candidatos[fonte.numero - 1].assunto}"
        f"\nJulgamento: {candidatos[fonte.numero - 1].data_julgamento}"
        f"\nEmenta: {fonte.texto}"
        for fonte in fontes
    ]
    mensagem = f"Pergunta:\n{pergunta}"
    if contexto:
        mensagem += f"\n\nContexto factual:\n{contexto}"
    mensagem += "\n\nCandidatos:\n" + "\n\n".join(blocos)
    return PacoteContextoIA(
        pergunta=pergunta,
        instrucoes_sistema=instrucoes_analise(tribunal),
        mensagem_usuario=mensagem,
        fontes=fontes,
    )


def validar_plano(dados: dict, config: ConfiguracaoPesquisaAssistida) -> dict:
    questoes = []
    for item in dados.get("questoes", [])[:5]:
        if isinstance(item, dict):
            pergunta = str(item.get("pergunta", "")).strip()[:300]
            opcoes = [
                str(op).strip()[:150]
                for op in item.get("opcoes", [])
                if str(op).strip()
            ][:6]
            if pergunta:
                questoes.append({"pergunta": pergunta, "opcoes": opcoes})
        elif isinstance(item, str) and item.strip():
            questoes.append(str(item).strip()[:300])

    consultas = []
    for item in dados.get("consultas", []):
        if not isinstance(item, dict):
            continue
        pesquisa = str(item.get("pesquisa", "")).strip()[:120]
        if pesquisa:
            consultas.append(
                {
                    "pesquisa": pesquisa,
                    "justificativa": str(item.get("justificativa", "")).strip()[:500],
                }
            )
    consultas = consultas[: config.max_consultas]
    precisa = bool(dados.get("precisa_esclarecimento"))
    if precisa and not questoes:
        questoes = [
            {
                "pergunta": "Quais são os fatos e a tese jurídica específica do caso?",
                "opcoes": [
                    "Relação de Consumo / CDC",
                    "Contratos e Obrigações Civis",
                    "Responsabilidade Civil e Indenização",
                    "Execução e Título Extrajudicial",
                ],
            }
        ]
    return {
        "precisa_esclarecimento": precisa,
        "questoes": questoes,
        "tema": str(dados.get("tema", "")).strip()[:300],
        "consultas": [] if precisa else consultas,
    }


def validar_analises(
    dados: dict,
    candidatos: list[Decisao],
    config: ConfiguracaoPesquisaAssistida,
) -> list[dict]:
    permitidos = {decisao.cd_acordao for decisao in candidatos}
    resultados = []
    vistos = set()
    for item in dados.get("resultados", []):
        if not isinstance(item, dict):
            continue
        cd_acordao = str(item.get("cd_acordao", "")).strip()
        if cd_acordao not in permitidos or cd_acordao in vistos:
            continue
        vistos.add(cd_acordao)
        try:
            relevancia = max(0.0, min(1.0, float(item.get("relevancia", 0))))
        except (TypeError, ValueError):
            relevancia = 0.0
        resultados.append(
            {
                "cd_acordao": cd_acordao,
                "relevancia": relevancia,
                "argumento": str(item.get("argumento", "")).strip()[:2_000],
                "aderencia_fatica": str(item.get("aderencia_fatica", "")).strip()[
                    :2_000
                ],
                "ressalva": str(item.get("ressalva", "")).strip()[:1_000],
            }
        )
    resultados.sort(key=lambda item: item["relevancia"], reverse=True)
    return resultados[: config.max_resultados]


def decisao_de_dict(dados: dict) -> Decisao:
    campos = {
        "processo",
        "cd_acordao",
        "cd_foro",
        "classe",
        "assunto",
        "relator",
        "comarca",
        "orgao_julgador",
        "data_julgamento",
        "data_publicacao",
        "ementa",
        "inteiro_teor_url",
        "ocorrencias",
    }
    valores = {campo: dados.get(campo, "") for campo in campos}
    valores["ocorrencias"] = dados.get("ocorrencias")
    return Decisao(**valores)


PRIORIDADE_TRIBUNAIS: tuple[str, ...] = (
    "tjsp",
    "stj",
    "stf",
    "tst",
    "tjrj",
    "tjmg",
    "tjrs",
    "tjpr",
    "tjsc",
    "tjba",
    "tjdft",
    "trf3",
    "trf4",
    "trf1",
    "trf2",
    "trf5",
    "trf6",
)


def buscar_candidatos_tribunais(
    servico_coleta,
    consultas: list[dict],
    tribunal: str = "todos",
    max_candidatos: int = 20,
    callback_progresso=None,
    timeout_tribunal: float = 7.0,
    max_candidatos_coleta: int = 40,
) -> tuple[list[Decisao], list[dict], dict[str, str]]:
    import concurrent.futures

    from .models import Consulta
    from .tribunais_config import TODOS_TJS, tribunais_ativos

    lotes: list[list[tuple[Decisao, str]]] = []
    executadas: list[dict] = []

    if not tribunal or tribunal.lower() in ("todos", "all"):
        tribs_alvo = list(TODOS_TJS)
    elif tribunal.lower() in ("todas_cortes", "todos_nacionais", "brasil"):
        tribs_alvo = list(tribunais_ativos())
    elif tribunal.lower() in ("superiores", "tribunais_superiores"):
        tribs_alvo = ["stf", "stj", "tst", "tse", "stm"]
    elif "," in tribunal:
        tribs_alvo = [t.strip().lower() for t in tribunal.split(",") if t.strip()]
    else:
        tribs_alvo = [tribunal.lower().strip()]

    ordem = {t: i for i, t in enumerate(PRIORIDADE_TRIBUNAIS)}
    tribs_alvo.sort(key=lambda t: ordem.get(t, 100))

    import inspect

    sig = inspect.signature(servico_coleta.pesquisar)
    aceita_var = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    extra_params = {}
    if "indexar_vetores" in sig.parameters or aceita_var:
        extra_params["indexar_vetores"] = False
    if "timeout" in sig.parameters or aceita_var:
        extra_params["timeout"] = timeout_tribunal

    def coletar_tribunal_consulta(item_consulta: dict, trib: str):
        try:
            resultado = servico_coleta.pesquisar(
                Consulta(pesquisa=item_consulta["pesquisa"]),
                paginas=1,
                tribunal=trib,
                **extra_params,
            )
            decisoes = [
                decisao_de_dict(dados) for dados in resultado.get("decisoes", [])
            ]
            return item_consulta, trib, resultado, decisoes
        except Exception:
            return item_consulta, trib, {}, []

    max_workers = min(32, max(1, len(consultas) * len(tribs_alvo)))
    total_coletados = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futuros = [
            executor.submit(coletar_tribunal_consulta, item, trib)
            for item in consultas
            for trib in tribs_alvo
        ]
        for f in concurrent.futures.as_completed(futuros):
            item_consulta, trib, resultado, decisoes = f.result()
            if decisoes:
                sigla = trib.upper()
                lotes.append([(d, sigla) for d in decisoes])
                total_coletados += len(decisoes)
                executadas.append(
                    {
                        **item_consulta,
                        "tribunal": sigla,
                        "consulta_id": resultado.get("consulta_id", 0),
                        "total_disponivel": resultado.get(
                            "total_disponivel", len(decisoes)
                        ),
                        "coletados": len(decisoes),
                    }
                )
                if callback_progresso:
                    pct = min(70, 20 + len(executadas) * 3)
                    callback_progresso(
                        "coleta",
                        pct,
                        f"Coletados {len(decisoes)} acórdãos ({sigla})...",
                    )
            if total_coletados >= max_candidatos_coleta and len(tribs_alvo) > 1:
                for pendente in futuros:
                    pendente.cancel()
                break

    candidatos: list[Decisao] = []
    tribunal_por_acordao: dict[str, str] = {}
    vistos: set[str] = set()

    for posicao in range(max((len(lote) for lote in lotes), default=0)):
        if len(candidatos) >= max_candidatos:
            break
        for lote in lotes:
            if posicao >= len(lote):
                continue
            decisao, sigla = lote[posicao]
            if decisao.cd_acordao in vistos:
                continue
            vistos.add(decisao.cd_acordao)
            tribunal_por_acordao[decisao.cd_acordao] = sigla
            candidatos.append(decisao)
            if len(candidatos) >= max_candidatos:
                break

    return candidatos, executadas, tribunal_por_acordao
