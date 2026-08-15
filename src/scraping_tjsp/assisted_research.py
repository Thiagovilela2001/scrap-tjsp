from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass

from .cost import PrecosTokens, estimar_custo_maximo, resumir_custo
from .models import Consulta, Decisao, ResultadoPesquisa
from .rag import FonteContexto, PacoteContextoIA, RespostaIA
from .storage import RepositorioSQLite

INSTRUCOES_PLANEJAMENTO = """Você planeja pesquisa jurisprudencial no TJSP.
Converta o relato em consultas curtas para o campo de pesquisa livre do CJSG.
Não invente IDs, processos, julgados ou fatos.
ICMS e outros temas amplos exigem tese, fatos e objetivo argumentativo específicos.
Se faltarem informações materiais, não gere consultas: peça esclarecimentos.
Responda somente em JSON válido, sem Markdown, neste formato:
{
  "precisa_esclarecimento": true ou false,
  "questoes": ["pergunta objetiva"],
  "tema": "síntese curta",
  "consultas": [
    {"pesquisa": "termos com até 120 caracteres", "justificativa": "motivo"}
  ]
}
Gere no máximo três consultas e cinco questões de esclarecimento."""

INSTRUCOES_ANALISE = """Você analisa candidatos de jurisprudência do TJSP.
Use somente as ementas fornecidas. Não afirme que uma decisão sustenta uma tese além
do que está expresso na ementa. Ranqueie aderência ao caso e explique como cada
processo pode contribuir como argumento, sempre indicando a necessidade de revisar
o inteiro teor. Responda somente em JSON válido, sem Markdown, neste formato:
{
  "resultados": [
    {
      "cd_acordao": "identificador fornecido",
      "relevancia": 0.0,
      "argumento": "possível uso argumentativo",
      "aderencia_fatica": "pontos de aproximação ou diferença",
      "ressalva": "limitação relevante"
    }
  ]
}
Retorne no máximo seis resultados, ordenados por relevância decrescente.
Seja conciso: cada campo textual deve ter no máximo 350 caracteres."""


class ErroPesquisaAssistida(RuntimeError):
    """Falha controlada no planejamento ou na análise da pesquisa."""


class LimiteCustoPesquisa(ErroPesquisaAssistida):
    def __init__(self, estimativa: float, limite: float) -> None:
        self.estimativa = estimativa
        self.limite = limite
        super().__init__(
            f"Pesquisa assistida pode custar até R$ {estimativa:.6f}; "
            f"limite informado: R$ {limite:.6f}."
        )


@dataclass(slots=True, frozen=True)
class ConfiguracaoPesquisaAssistida:
    max_consultas: int = 3
    max_candidatos: int = 20
    max_resultados: int = 6
    tokens_planejamento: int = 500
    tokens_analise: int = 1_500
    caracteres_ementa: int = 1_200


class PesquisaAssistidaTJSP:
    def __init__(
        self,
        repositorio: RepositorioSQLite,
        servico_coleta,
        provedor_factory: Callable[[str | None, int], object],
        *,
        configuracao: ConfiguracaoPesquisaAssistida | None = None,
        precos: PrecosTokens | None = None,
    ) -> None:
        self.repositorio = repositorio
        self.servico_coleta = servico_coleta
        self.provedor_factory = provedor_factory
        self.config = configuracao or ConfiguracaoPesquisaAssistida()
        self.precos = precos or PrecosTokens()

    def pesquisar(
        self,
        pergunta: str,
        *,
        contexto_caso: str = "",
        modelo: str | None = None,
        max_custo_brl: float = 0.20,
    ) -> dict:
        pergunta = pergunta.strip()
        contexto_caso = contexto_caso.strip()
        if len(pergunta) < 5:
            raise ValueError("Pergunta deve ter pelo menos 5 caracteres.")
        if max_custo_brl <= 0:
            raise ValueError("Teto de custo deve ser positivo.")

        pacote_plano = _pacote_planejamento(pergunta, contexto_caso)
        estimativa_maxima = self._estimar_maximo(pacote_plano)
        if estimativa_maxima > max_custo_brl:
            raise LimiteCustoPesquisa(estimativa_maxima, max_custo_brl)

        provedor_plano = self.provedor_factory(
            modelo,
            self.config.tokens_planejamento,
        )
        resposta_plano, auditoria_plano = self._responder_auditado(
            pacote_plano,
            provedor_plano,
            etapa="planejamento",
            max_custo_brl=max_custo_brl,
            estimativa_maxima=estimativa_maxima,
        )
        plano = _validar_plano(_carregar_json(resposta_plano.texto), self.config)
        if plano["precisa_esclarecimento"] or not plano["consultas"]:
            return {
                "status": "precisa_esclarecimento",
                "tema": plano["tema"],
                "questoes": plano["questoes"],
                "consultas": [],
                "processos": [],
                "auditorias_ia": [auditoria_plano],
                "custo": resumir_custo(
                    [resposta_plano],
                    precos=self.precos,
                    estimativa_maxima=estimativa_maxima,
                    limite_brl=max_custo_brl,
                ),
            }

        candidatos, consultas_executadas = self._buscar_candidatos(plano["consultas"])
        if not candidatos:
            return {
                "status": "sem_resultados",
                "tema": plano["tema"],
                "questoes": [],
                "consultas": consultas_executadas,
                "processos": [],
                "auditorias_ia": [auditoria_plano],
                "custo": resumir_custo(
                    [resposta_plano],
                    precos=self.precos,
                    estimativa_maxima=estimativa_maxima,
                    limite_brl=max_custo_brl,
                ),
            }

        consulta_id = self.repositorio.salvar_pesquisa(
            Consulta(pesquisa=(f"pesquisa assistida: {pergunta}")[:120]),
            ResultadoPesquisa(
                total_disponivel=len(candidatos),
                paginas_coletadas=len(consultas_executadas),
                decisoes=tuple(candidatos),
            ),
        )
        pacote_analise = _pacote_analise(
            pergunta, contexto_caso, candidatos, self.config
        )
        provedor_analise = self.provedor_factory(
            modelo,
            self.config.tokens_analise,
        )
        resposta_analise, auditoria_analise = self._responder_auditado(
            pacote_analise,
            provedor_analise,
            etapa="analise_candidatos",
            max_custo_brl=max_custo_brl,
            estimativa_maxima=estimativa_maxima,
        )
        dados_analise = _carregar_json(
            resposta_analise.texto,
            permitir_resultados_parciais=True,
        )
        analises = _validar_analises(
            dados_analise,
            candidatos,
            self.config,
        )
        por_acordao = {decisao.cd_acordao: decisao for decisao in candidatos}
        processos = [
            {
                **por_acordao[item["cd_acordao"]].como_dict(),
                **item,
            }
            for item in analises
        ]
        return {
            "status": "concluida",
            "tema": plano["tema"],
            "questoes": [],
            "consultas": consultas_executadas,
            "consulta_id": consulta_id,
            "total_candidatos": len(candidatos),
            "analise_parcial": bool(dados_analise.get("_resposta_parcial")),
            "processos": processos,
            "auditorias_ia": [auditoria_plano, auditoria_analise],
            "custo": resumir_custo(
                [resposta_plano, resposta_analise],
                precos=self.precos,
                estimativa_maxima=estimativa_maxima,
                limite_brl=max_custo_brl,
            ),
        }

    def _estimar_maximo(self, pacote_plano: PacoteContextoIA) -> float:
        pacote_maximo = PacoteContextoIA(
            pergunta="estimativa",
            instrucoes_sistema=INSTRUCOES_ANALISE,
            mensagem_usuario="x"
            * (self.config.max_candidatos * self.config.caracteres_ementa),
            fontes=(),
        )
        return estimar_custo_maximo(
            [pacote_plano],
            max_output_tokens=self.config.tokens_planejamento,
            precos=self.precos,
        ) + estimar_custo_maximo(
            [pacote_maximo],
            max_output_tokens=self.config.tokens_analise,
            precos=self.precos,
        )

    def _buscar_candidatos(
        self, consultas: list[dict]
    ) -> tuple[list[Decisao], list[dict]]:
        lotes: list[list[Decisao]] = []
        executadas: list[dict] = []
        for item in consultas:
            resultado = self.servico_coleta.pesquisar(
                Consulta(pesquisa=item["pesquisa"]),
                paginas=1,
            )
            decisoes = [_decisao_de_dict(dados) for dados in resultado["decisoes"]]
            lotes.append(decisoes)
            executadas.append(
                {
                    **item,
                    "consulta_id": resultado["consulta_id"],
                    "total_disponivel": resultado["total_disponivel"],
                    "coletados": len(decisoes),
                }
            )

        candidatos: list[Decisao] = []
        vistos: set[str] = set()
        for posicao in range(max((len(lote) for lote in lotes), default=0)):
            for lote in lotes:
                if posicao >= len(lote):
                    continue
                decisao = lote[posicao]
                if decisao.cd_acordao in vistos:
                    continue
                vistos.add(decisao.cd_acordao)
                candidatos.append(decisao)
                if len(candidatos) >= self.config.max_candidatos:
                    return candidatos, executadas
        return candidatos, executadas

    def _responder_auditado(
        self,
        pacote: PacoteContextoIA,
        provedor,
        *,
        etapa: str,
        max_custo_brl: float,
        estimativa_maxima: float,
    ) -> tuple[RespostaIA, int]:
        execucao_id = self.repositorio.iniciar_execucao_ia(
            pacote,
            provedor="maritaca",
            modelo=provedor.modelo,
            configuracao={
                "tipo": "pesquisa_assistida_tjsp",
                "etapa": etapa,
                "max_custo_brl": max_custo_brl,
                "estimativa_maxima_total_brl": round(estimativa_maxima, 6),
            },
        )
        try:
            resposta = provedor.responder(pacote)
        except Exception as exc:
            self.repositorio.falhar_execucao_ia(
                execucao_id,
                str(exc),
                duracao_ms=getattr(exc, "duracao_ms", None),
            )
            raise
        self.repositorio.concluir_execucao_ia(execucao_id, resposta)
        return resposta, execucao_id


def _pacote_planejamento(pergunta: str, contexto: str) -> PacoteContextoIA:
    mensagem = f"Pergunta de pesquisa:\n{pergunta}"
    if contexto:
        mensagem += f"\n\nContexto factual do caso:\n{contexto}"
    return PacoteContextoIA(
        pergunta=pergunta,
        instrucoes_sistema=INSTRUCOES_PLANEJAMENTO,
        mensagem_usuario=mensagem,
        fontes=(),
    )


def _pacote_analise(
    pergunta: str,
    contexto: str,
    candidatos: list[Decisao],
    config: ConfiguracaoPesquisaAssistida,
) -> PacoteContextoIA:
    fontes = tuple(
        FonteContexto(
            numero=numero,
            id=f"acordao:{decisao.cd_acordao}",
            citacao=(f"Processo {decisao.processo}, acórdão {decisao.cd_acordao}"),
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
        instrucoes_sistema=INSTRUCOES_ANALISE,
        mensagem_usuario=mensagem,
        fontes=fontes,
    )


def _carregar_json(
    texto: str,
    *,
    permitir_resultados_parciais: bool = False,
) -> dict:
    limpo = texto.strip()
    limpo = re.sub(r"^```(?:json)?\s*", "", limpo, flags=re.IGNORECASE)
    limpo = re.sub(r"\s*```$", "", limpo)
    inicio = limpo.find("{")
    fim = limpo.rfind("}")
    if inicio < 0 or fim < inicio:
        raise ErroPesquisaAssistida("Maritaca não devolveu JSON válido.")
    try:
        dados = json.loads(limpo[inicio : fim + 1])
    except json.JSONDecodeError as exc:
        if permitir_resultados_parciais:
            parcial = _carregar_resultados_parciais(limpo)
            if parcial is not None:
                return parcial
        raise ErroPesquisaAssistida(
            f"Maritaca devolveu JSON inválido: {exc.msg}."
        ) from exc
    if not isinstance(dados, dict):
        raise ErroPesquisaAssistida("Resposta estruturada deve ser um objeto JSON.")
    return dados


def _carregar_resultados_parciais(texto: str) -> dict | None:
    chave = re.search(r'"resultados"\s*:\s*\[', texto)
    if chave is None:
        return None
    posicao = chave.end()
    decoder = json.JSONDecoder()
    resultados = []
    while posicao < len(texto):
        while posicao < len(texto) and texto[posicao] in " \t\r\n,":
            posicao += 1
        if posicao >= len(texto) or texto[posicao] == "]":
            break
        if texto[posicao] != "{":
            break
        try:
            item, fim = decoder.raw_decode(texto, posicao)
        except json.JSONDecodeError:
            break
        if isinstance(item, dict):
            resultados.append(item)
        posicao = fim
    if not resultados:
        return None
    return {"resultados": resultados, "_resposta_parcial": True}


def _validar_plano(dados: dict, config: ConfiguracaoPesquisaAssistida) -> dict:
    questoes = [
        str(item).strip()[:300]
        for item in dados.get("questoes", [])
        if str(item).strip()
    ][:5]
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
        questoes = ["Quais são os fatos e a tese jurídica específica do caso?"]
    return {
        "precisa_esclarecimento": precisa,
        "questoes": questoes,
        "tema": str(dados.get("tema", "")).strip()[:300],
        "consultas": [] if precisa else consultas,
    }


def _validar_analises(
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


def _decisao_de_dict(dados: dict) -> Decisao:
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
