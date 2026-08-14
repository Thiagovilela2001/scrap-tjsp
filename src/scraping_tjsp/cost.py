from __future__ import annotations

from dataclasses import dataclass
from math import fsum

from .rag import PacoteContextoIA, RespostaIA

MARGEM_TOKENS_MENSAGEM = 128
FONTE_PRECOS = "https://docs.maritaca.ai/pt/precos"
DATA_VERIFICACAO_PRECOS = "2026-08-14"


@dataclass(slots=True, frozen=True)
class PrecosTokens:
    entrada_milhao: float = 5.0
    saida_milhao: float = 20.0

    def __post_init__(self) -> None:
        if self.entrada_milhao < 0 or self.saida_milhao < 0:
            raise ValueError("Preços de tokens não podem ser negativos.")

    def calcular(self, tokens_entrada: int, tokens_saida: int) -> float:
        return (
            tokens_entrada * self.entrada_milhao + tokens_saida * self.saida_milhao
        ) / 1_000_000


def estimar_custo_maximo(
    pacotes: list[PacoteContextoIA],
    *,
    max_output_tokens: int,
    precos: PrecosTokens,
) -> float:
    if max_output_tokens < 1:
        raise ValueError("Máximo de tokens de saída deve ser positivo.")
    return fsum(
        precos.calcular(
            _limite_conservador_tokens_entrada(pacote),
            max_output_tokens,
        )
        for pacote in pacotes
    )


def resumir_custo(
    respostas: list[RespostaIA],
    *,
    precos: PrecosTokens,
    estimativa_maxima: float | None,
    limite_brl: float | None,
) -> dict:
    tokens_entrada = sum(resposta.tokens_entrada or 0 for resposta in respostas)
    tokens_saida = sum(resposta.tokens_saida or 0 for resposta in respostas)
    tokens_total = sum(resposta.tokens_total or 0 for resposta in respostas)
    sem_contagem = sum(
        resposta.tokens_entrada is None or resposta.tokens_saida is None
        for resposta in respostas
    )
    return {
        "chamadas_concluidas": len(respostas),
        "chamadas_sem_contagem": sem_contagem,
        "tokens_entrada": tokens_entrada,
        "tokens_saida": tokens_saida,
        "tokens_total": tokens_total,
        "preco_entrada_milhao_brl": precos.entrada_milhao,
        "preco_saida_milhao_brl": precos.saida_milhao,
        "fonte_precos": FONTE_PRECOS,
        "data_verificacao_precos": DATA_VERIFICACAO_PRECOS,
        "estimativa_maxima_pre_execucao_brl": (
            round(estimativa_maxima, 6) if estimativa_maxima is not None else None
        ),
        "limite_brl": limite_brl,
        "custo_padrao_estimado_brl": round(
            precos.calcular(tokens_entrada, tokens_saida), 6
        ),
    }


def _limite_conservador_tokens_entrada(pacote: PacoteContextoIA) -> int:
    conteudo = f"{pacote.instrucoes_sistema}\n{pacote.mensagem_usuario}"
    return len(conteudo.encode("utf-8")) + MARGEM_TOKENS_MENSAGEM
