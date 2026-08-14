from types import SimpleNamespace

import pytest

from scraping_tjsp.maritaca import ErroMaritaca, ProvedorMaritaca
from scraping_tjsp.rag import PacoteContextoIA


class RespostasFalsas:
    def __init__(self):
        self.parametros = None

    def create(self, **kwargs):
        self.parametros = kwargs
        return SimpleNamespace(output_text="Resposta jurídica com [Fonte 1].")


class ClienteFalso:
    def __init__(self):
        self.responses = RespostasFalsas()


def _pacote() -> PacoteContextoIA:
    return PacoteContextoIA(
        pergunta="Qual fundamento?",
        instrucoes_sistema="Use somente as fontes.",
        mensagem_usuario="Pergunta e [Fonte 1].",
        fontes=(),
    )


def test_envia_pacote_rag_para_responses_api():
    cliente = ClienteFalso()
    provedor = ProvedorMaritaca(
        api_key="chave-teste",
        modelo="sabia-4",
        max_output_tokens=500,
        cliente=cliente,
    )

    resposta = provedor.responder(_pacote())

    assert resposta == "Resposta jurídica com [Fonte 1]."
    assert cliente.responses.parametros == {
        "model": "sabia-4",
        "instructions": "Use somente as fontes.",
        "input": "Pergunta e [Fonte 1].",
        "max_output_tokens": 500,
    }


def test_exige_chave_sem_expor_segredo(monkeypatch):
    monkeypatch.delenv("MARITACA_API_KEY", raising=False)

    with pytest.raises(ErroMaritaca, match="MARITACA_API_KEY"):
        ProvedorMaritaca(cliente=ClienteFalso())
