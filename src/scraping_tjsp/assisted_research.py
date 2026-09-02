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
Defina precisa_esclarecimento como true SOMENTE se a pergunta for excessivamente curta ou genérica (ex: apenas uma palavra como "icms", "banco", "dano moral") sem qualquer contexto fático.
Se a pergunta contiver fatos mínimos, especificações ou detalhes do caso, defina precisa_esclarecimento como false, defina questoes como [] (lista vazia) e SEMPRE gere entre 1 e 3 consultas objetivas para o TJSP.
Se precisa_esclarecimento for true, defina consultas como [] (lista vazia) e gere até 3 questões de esclarecimento com até 4 opções cada.
Responda somente em JSON válido, sem Markdown, neste formato:
{
  "precisa_esclarecimento": true ou false,
  "questoes": [
    {
      "pergunta": "Qual a situação fática ou ponto controvertido?",
      "opcoes": ["Opção 1", "Opção 2", "Opção 3", "Opção 4"]
    }
  ],
  "tema": "síntese curta",
  "consultas": [
    {"pesquisa": "termos com até 120 caracteres", "justificativa": "motivo"}
  ]
}
Gere no máximo três consultas ou três questões de esclarecimento."""

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
        tribunal: str = "tjsp",
        callback_progresso: Callable[[str, int, str], None] | None = None,
    ) -> dict:
        pergunta = pergunta.strip()
        contexto_caso = contexto_caso.strip()
        trib_upper = tribunal.upper()
        if not pergunta:
            raise ValueError("Pergunta não pode ser vazia.")
        if max_custo_brl <= 0:
            raise ValueError("Teto de custo deve ser positivo.")

        if callback_progresso:
            callback_progresso(
                "planejamento", 15, f"Planejando consultas jurídicas para o {trib_upper}..."
            )

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
            if callback_progresso:
                callback_progresso(
                    "esclarecimento", 100, "Esclarecimentos necessários."
                )
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

        if callback_progresso:
            callback_progresso(
                "coleta", 45, f"Consultando jurisprudência no {trib_upper}..."
            )

        candidatos, consultas_executadas = self._buscar_candidatos(plano["consultas"], tribunal=tribunal)
        if not candidatos:
            if callback_progresso:
                callback_progresso(
                    "sem_resultados", 100, "Nenhum acórdão encontrado no TJSP."
                )
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

        if callback_progresso:
            callback_progresso(
                "analise", 75, "Analisando relevância dos precedentes..."
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
        trib_map = getattr(self, "_tribunal_por_acordao", {})
        processos = [
            {
                "tribunal": trib_map.get(item["cd_acordao"]) or (trib_upper if trib_upper != "TODOS" else "TJSP"),
                **por_acordao[item["cd_acordao"]].como_dict(),
                **item,
            }
            for item in analises
        ]

        if callback_progresso:
            callback_progresso("conclusao", 100, "Pesquisa concluída.")

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

    def pesquisar_stream(
        self,
        pergunta: str,
        *,
        contexto_caso: str = "",
        modelo: str | None = None,
        max_custo_brl: float = 0.20,
        tribunal: str = "tjsp",
    ):
        trib_upper = tribunal.upper()
        yield {
            "tipo": "progresso",
            "etapa": "planejamento",
            "progresso": 15,
            "mensagem": f"Planejando consultas jurídicas com IA ({trib_upper})...",
        }
        resultado = self.pesquisar(
            pergunta,
            contexto_caso=contexto_caso,
            modelo=modelo,
            max_custo_brl=max_custo_brl,
            tribunal=tribunal,
        )
        yield {
            "tipo": "progresso",
            "etapa": "conclusao",
            "progresso": 100,
            "mensagem": f"Pesquisa concluída ({trib_upper}).",
        }
        yield {"tipo": "resultado", "dados": resultado}

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
        self, consultas: list[dict], tribunal: str = "todos"
    ) -> tuple[list[Decisao], list[dict]]:
        import concurrent.futures

        lotes: list[list[tuple[Decisao, str]]] = []
        executadas: list[dict] = []

        # Tribunais ativos comprovados
        tribs_alvo = (
            ["tjsp", "tjms", "tjam", "tjac"]
            if tribunal in ("todos", "all", "", None)
            else [tribunal.lower().strip()]
        )

        def coletar_tribunal_consulta(item_consulta: dict, trib: str):
            try:
                resultado = self.servico_coleta.pesquisar(
                    Consulta(pesquisa=item_consulta["pesquisa"]),
                    paginas=1,
                    tribunal=trib,
                )
                decisoes = [_decisao_de_dict(dados) for dados in resultado.get("decisoes", [])]
                return item_consulta, trib, resultado, decisoes
            except Exception:
                return item_consulta, trib, {}, []

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
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
                    executadas.append(
                        {
                            **item_consulta,
                            "tribunal": sigla,
                            "consulta_id": resultado.get("consulta_id", 0),
                            "total_disponivel": resultado.get("total_disponivel", len(decisoes)),
                            "coletados": len(decisoes),
                        }
                    )

        candidatos: list[Decisao] = []
        tribunal_por_acordao: dict[str, str] = {}
        vistos: set[str] = set()

        for posicao in range(max((len(lote) for lote in lotes), default=0)):
            if len(candidatos) >= self.config.max_candidatos:
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
                if len(candidatos) >= self.config.max_candidatos:
                    break
        self._tribunal_por_acordao = tribunal_por_acordao
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


def _reparar_json_string(s: str) -> str:
    s = re.sub(r"//.*?(\r\n|\n|$)", "\n", s)
    s = re.sub(r"\bTrue\b", "true", s)
    s = re.sub(r"\bFalse\b", "false", s)
    s = re.sub(r"\bNone\b", "null", s)
    s = re.sub(r",\s*([\]}])", r"\1", s)
    return s


def _fechar_json_truncado(s: str) -> str:
    in_string = False
    escape = False
    stack: list[str] = []
    for c in s:
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if not in_string:
            if c in "{[":
                stack.append("}" if c == "{" else "]")
            elif c in "}]":
                if stack and stack[-1] == c:
                    stack.pop()
    if in_string:
        s += '"'
    while stack:
        s += stack.pop()
    return s


def _extrair_plano_fallback(texto: str) -> dict | None:
    consultas = []
    for m in re.finditer(r'"pesquisa"\s*:\s*"([^"]+)"', texto):
        pesq = m.group(1).strip()
        if pesq:
            consultas.append({"pesquisa": pesq, "justificativa": ""})
    tema_match = re.search(r'"tema"\s*:\s*"([^"]+)"', texto)
    tema = tema_match.group(1).strip() if tema_match else "Pesquisa jurisprudencial"
    escl_match = re.search(
        r'"precisa_esclarecimento"\s*:\s*(true|false)', texto, re.IGNORECASE
    )
    escl = escl_match.group(1).lower() == "true" if escl_match else False
    if consultas or escl:
        return {
            "precisa_esclarecimento": escl,
            "tema": tema,
            "questoes": [],
            "consultas": consultas[:3],
        }
    return None


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

    # 1. Tentativa direta se encontrar delimitadores
    if inicio >= 0 and fim >= inicio:
        candidato = limpo[inicio : fim + 1]
        try:
            dados = json.loads(candidato)
            if isinstance(dados, dict):
                return dados
        except json.JSONDecodeError:
            pass

        # 2. Tentativa com limpeza de comentários/vírgulas/booleans
        reparado = _reparar_json_string(candidato)
        try:
            dados = json.loads(reparado)
            if isinstance(dados, dict):
                return dados
        except json.JSONDecodeError:
            pass

    # 3. Resultados parciais se análise
    if permitir_resultados_parciais:
        parcial = _carregar_resultados_parciais(limpo)
        if parcial is not None:
            return parcial

    # 4. Se JSON estiver truncado
    if inicio >= 0:
        candidato = _fechar_json_truncado(_reparar_json_string(limpo[inicio:]))
        try:
            dados = json.loads(candidato)
            if isinstance(dados, dict):
                return dados
        except json.JSONDecodeError:
            pass

    # 5. Fallback para plano de pesquisa
    plano_fallback = _extrair_plano_fallback(limpo)
    if plano_fallback is not None:
        return plano_fallback

    raise ErroPesquisaAssistida("Maritaca não devolveu JSON válido estruturado.")


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
