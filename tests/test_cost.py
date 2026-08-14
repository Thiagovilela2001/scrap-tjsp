import pytest

from scraping_tjsp.cost import PrecosTokens, estimar_custo_maximo, resumir_custo
from scraping_tjsp.rag import PacoteContextoIA, RespostaIA


def _pacote() -> PacoteContextoIA:
    return PacoteContextoIA(
        pergunta="Pergunta?",
        instrucoes_sistema="Use fontes.",
        mensagem_usuario="Texto jurídico.",
        fontes=(),
    )


def test_estima_teto_conservador_antes_da_chamada():
    precos = PrecosTokens(entrada_milhao=5, saida_milhao=20)

    custo = estimar_custo_maximo(
        [_pacote(), _pacote()],
        max_output_tokens=100,
        precos=precos,
    )

    assert custo > precos.calcular(0, 200)


def test_resume_custo_com_tokens_reais():
    resposta = RespostaIA(
        texto="Resposta [Fonte 1].",
        provedor="maritaca",
        modelo="sabia-4",
        tokens_entrada=1_000,
        tokens_saida=200,
        tokens_total=1_200,
    )

    resumo = resumir_custo(
        [resposta],
        precos=PrecosTokens(entrada_milhao=5, saida_milhao=20),
        estimativa_maxima=0.1,
        limite_brl=0.2,
    )

    assert resumo["custo_padrao_estimado_brl"] == pytest.approx(0.009)
    assert resumo["tokens_total"] == 1_200
    assert resumo["chamadas_sem_contagem"] == 0
    assert resumo["fonte_precos"] == "https://docs.maritaca.ai/pt/precos"


def test_recusa_preco_negativo():
    with pytest.raises(ValueError, match="não podem ser negativos"):
        PrecosTokens(entrada_milhao=-1)
