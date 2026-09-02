from scraping_tjsp.legal_validation import validar_resposta_juridica
from scraping_tjsp.rag import FonteContexto


def _fontes():
    return (
        FonteContexto(
            numero=1,
            id="acordao:19200575:pagina:7:chunk:1",
            citacao=("Processo 1035947-80.2016.8.26.0053, acórdão 19200575, p. 7"),
            url="/documentos/19200575",
            texto=(
                "Aplicação do Tema 176 e da Súmula 391. Os artigos 168 e 165 "
                "do CTN autorizam restituição de 12,5% e R$ 1.234,56."
            ),
            score_hibrido=0.03,
        ),
    )


def test_valida_citacao_identificadores_e_numeros_presentes_na_fonte():
    resposta = (
        "O processo 1035947-80.2016.8.26.0053, acórdão 19200575, aplica "
        "o Tema 176, a Súmula 391 e o art. 168 na página 7, com referência "
        "a 12,5% e R$ 1.234,56 [Fonte 1]."
    )

    validacao = validar_resposta_juridica(resposta, _fontes())

    assert validacao["aprovada"] is True
    assert validacao["fontes_citadas"] == [1]
    assert validacao["referencias_nao_verificadas"] == []


def test_rejeita_fonte_processo_e_tema_inventados():
    resposta = (
        "O processo 9999999-99.2026.8.26.0000 aplica o Tema 9999 "
        "na página 40 [Fonte 2]."
    )

    validacao = validar_resposta_juridica(resposta, _fontes())

    assert validacao["aprovada"] is False
    assert validacao["citacoes_invalidas"] == [2]
    assert {item["tipo"] for item in validacao["referencias_nao_verificadas"]} == {
        "processo",
        "tema",
        "pagina",
    }


def test_exige_ao_menos_uma_citacao_de_fonte():
    validacao = validar_resposta_juridica("Fundamento genérico.", _fontes())

    assert validacao["aprovada"] is False
