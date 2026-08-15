import json

from scraping_tjsp.embedding_comparison_cli import comparar_relatorios, main


def _relatorio(modelo: str, recall: float, mrr: float) -> dict:
    return {
        "configuracao": {"embedding_model": modelo},
        "resumo": {
            "taxa_aprovacao": 0.5,
            "recall_medio": recall,
            "mrr_medio": mrr,
            "cobertura_termos_contexto_media": 0.75,
        },
    }


def test_compara_metricas_e_identifica_modelos():
    resultado = comparar_relatorios(
        _relatorio("all-MiniLM-L6-v2", 0.6, 0.5),
        _relatorio("BAAI/bge-m3", 0.8, 0.7),
    )

    assert resultado["base"]["embedding_model"] == "all-MiniLM-L6-v2"
    assert resultado["candidato"]["embedding_model"] == "BAAI/bge-m3"
    assert resultado["deltas_candidato_menos_base"]["recall_medio"] == 0.2
    assert resultado["deltas_candidato_menos_base"]["mrr_medio"] == 0.2


def test_cli_grava_comparacao(tmp_path):
    base = tmp_path / "base.json"
    candidato = tmp_path / "candidato.json"
    saida = tmp_path / "comparacao.json"
    base.write_text(json.dumps(_relatorio("mini", 0.4, 0.3)), encoding="utf-8")
    candidato.write_text(json.dumps(_relatorio("bge", 0.5, 0.6)), encoding="utf-8")

    codigo = main([str(base), str(candidato), "--saida", str(saida)])

    assert codigo == 0
    assert json.loads(saida.read_text(encoding="utf-8"))["candidato"][
        "embedding_model"
    ] == "bge"
