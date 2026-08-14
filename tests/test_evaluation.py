import json
from pathlib import Path

import pytest

from scraping_tjsp.evaluation import (
    AvaliadorJuridico,
    CasoAvaliacao,
    JuizJuridicoIA,
    carregar_casos,
)
from scraping_tjsp.evaluation_cli import construir_parser, main
from scraping_tjsp.rag import FonteContexto, PacoteContextoIA, RespostaIA


def _caso() -> CasoAvaliacao:
    return CasoAvaliacao.de_dict(
        {
            "caso_id": "caso-1",
            "pergunta": "Quando cabem embargos?",
            "acordaos_relevantes": ["123"],
            "chunks_relevantes": [],
            "termos_esperados": ["omissão", "contradição"],
            "resposta_referencia": "Cabem em caso de omissão ou contradição.",
            "min_recall": 1,
            "min_cobertura_termos": 1,
        }
    )


def _pacote() -> PacoteContextoIA:
    return PacoteContextoIA(
        pergunta="Quando cabem embargos?",
        instrucoes_sistema="Use fontes.",
        mensagem_usuario="Fontes.",
        fontes=(
            FonteContexto(
                1,
                "acordao:123:pagina:4:chunk:1",
                "Processo X, acórdão 123, p. 4",
                "https://example.test",
                "Embargos cabem em caso de omissão ou contradição.",
                0.03,
            ),
        ),
    )


def test_avalia_recuperacao_resposta_e_citacoes():
    resposta = RespostaIA(
        texto="Cabem diante de omissão ou contradição [Fonte 1].",
        provedor="maritaca",
        modelo="sabia-4",
    )

    resultado = AvaliadorJuridico().avaliar(_caso(), _pacote(), resposta=resposta)

    assert resultado["aprovado"] is True
    assert resultado["recall"] == 1
    assert resultado["mrr"] == 1
    assert resultado["metricas_resposta"]["precisao_citacoes"] == 1
    assert resultado["metricas_resposta"]["cobertura_termos"] == 1


def test_interpreta_juiz_json_e_valida_notas():
    resposta = RespostaIA(
        texto=(
            '```json\n{"aderencia_fontes":1,"correcao_juridica":0.8,'
            '"completude":0.7,"qualidade_citacoes":0.9,'
            '"justificativa":"Adequada."}\n```'
        ),
        provedor="maritaca",
        modelo="sabia-4",
    )

    resultado = JuizJuridicoIA.interpretar(resposta)

    assert resultado["score_geral"] == pytest.approx(0.85)


def test_aceita_citacoes_agrupadas_e_alternativas_lexicais():
    pacote = _pacote()
    caso = CasoAvaliacao.de_dict(
        {
            "caso_id": "alternativas",
            "pergunta": "Quando cabem embargos?",
            "acordaos_relevantes": ["123"],
            "termos_esperados": ["prova técnica|omissão"],
            "min_cobertura_termos": 1,
        }
    )
    resposta = RespostaIA(
        texto="Há omissão relevante [Fonte 1, Fonte 1].",
        provedor="maritaca",
        modelo="sabia-4",
    )

    resultado = AvaliadorJuridico().avaliar(caso, pacote, resposta=resposta)

    assert resultado["aprovado"] is True
    assert resultado["metricas_resposta"]["precisao_citacoes"] == 1


def test_carrega_dataset_jsonl(tmp_path: Path):
    caminho = tmp_path / "casos.jsonl"
    caminho.write_text(
        '{"caso_id":"1","pergunta":"Pergunta?","acordaos_relevantes":["123"]}\n',
        encoding="utf-8",
    )

    casos = carregar_casos(caminho)

    assert casos[0].caso_id == "1"


def test_dataset_juridico_tem_vinte_fontes_rastreaveis():
    caminho = Path(__file__).parents[1] / "evals" / "casos.jsonl"

    casos = carregar_casos(caminho)
    linhas = [
        json.loads(linha) for linha in caminho.read_text(encoding="utf-8").splitlines()
    ]

    assert len(casos) == 20
    assert len({caso.acordaos_relevantes[0] for caso in casos}) == 20
    assert sum(not caso.filtros for caso in casos) == 5
    assert all(item["processo"] for item in linhas)
    assert all(
        item["fonte_url"].startswith("https://esaj.tjsp.jus.br/cjsg/getArquivo.do?")
        for item in linhas
    )


def test_parser_aceita_limite_de_casos():
    args = construir_parser().parse_args(["casos.jsonl", "--max-casos", "5"])

    assert args.max_casos == 5


def test_cli_recusa_limite_de_casos_invalido():
    with pytest.raises(SystemExit):
        main(["casos.jsonl", "--max-casos", "0"])


def test_cli_exige_geracao_para_limite_de_custo():
    with pytest.raises(SystemExit):
        main(["casos.jsonl", "--max-custo-brl", "0.20"])


def test_cli_recusa_limite_de_custo_com_juiz():
    with pytest.raises(SystemExit):
        main(
            [
                "casos.jsonl",
                "--gerar-respostas",
                "--juiz-ia",
                "--max-custo-brl",
                "0.20",
            ]
        )
