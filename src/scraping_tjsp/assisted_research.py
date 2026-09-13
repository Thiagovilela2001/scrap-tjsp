from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .cost import PrecosTokens, estimar_custo_maximo, resumir_custo
from .models import Consulta, Decisao, ResultadoPesquisa
from .prompts import (
    INSTRUCOES_ANALISE,
    carregar_json,
)
from .rag import PacoteContextoIA, RespostaIA
from .research_ranking import (
    buscar_candidatos_tribunais,
    decisao_de_dict,
    pacote_analise,
    pacote_planejamento,
    validar_analises,
    validar_plano,
)
from .storage import RepositorioSQLite
from .tribunais_config import TODOS_TJS

# Aliases para compatibilidade retroativa
_carregar_json = carregar_json
_validar_plano = validar_plano
_validar_analises = validar_analises
_decisao_de_dict = decisao_de_dict
_pacote_planejamento = pacote_planejamento
_pacote_analise = pacote_analise

TRIBUNAIS_PADRAO_TODOS: tuple[str, ...] = TODOS_TJS


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
                "planejamento",
                15,
                f"Planejando consultas jurídicas para o {trib_upper}...",
            )

        pacote_plano = _pacote_planejamento(pergunta, contexto_caso, tribunal=tribunal)
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

        candidatos, consultas_executadas = self._buscar_candidatos(
            plano["consultas"], tribunal=tribunal
        )
        if not candidatos:
            if callback_progresso:
                callback_progresso(
                    "sem_resultados",
                    100,
                    f"Nenhum acórdão encontrado no(s) tribunal(is) {trib_upper}.",
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
            pergunta, contexto_caso, candidatos, self.config, tribunal=tribunal
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
                "tribunal": trib_map.get(item["cd_acordao"])
                or (trib_upper if trib_upper != "TODOS" else "TJSP"),
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
        candidatos, executadas, mapa = buscar_candidatos_tribunais(
            self.servico_coleta,
            consultas,
            tribunal=tribunal,
            max_candidatos=self.config.max_candidatos,
        )
        self._tribunal_por_acordao = mapa
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
