from pathlib import Path

from scraping_tjsp.rag import FonteContexto, PacoteContextoIA, RespostaIA
from scraping_tjsp.storage import RepositorioSQLite


def _pacote() -> PacoteContextoIA:
    return PacoteContextoIA(
        pergunta="Qual fundamento?",
        instrucoes_sistema="Use fontes.",
        mensagem_usuario="Pergunta e fontes.",
        fontes=(
            FonteContexto(
                numero=1,
                id="acordao:123:pagina:2:chunk:1",
                citacao="Processo X, acórdão 123, p. 2",
                url="https://esaj.tjsp.jus.br/cjsg/getArquivo.do",
                texto="Fundamento jurídico.",
                score_hibrido=0.03,
            ),
        ),
    )


def test_audita_resposta_fontes_tokens_e_configuracao(tmp_path: Path):
    repositorio = RepositorioSQLite(tmp_path / "tjsp.sqlite3")
    repositorio.inicializar()
    execucao_id = repositorio.iniciar_execucao_ia(
        _pacote(),
        provedor="maritaca",
        modelo="sabia-4",
        configuracao={"limite_fontes": 6},
    )
    repositorio.concluir_execucao_ia(
        execucao_id,
        RespostaIA(
            texto="Resposta [Fonte 1].",
            provedor="maritaca",
            modelo="sabia-4",
            resposta_id="resp-1",
            tokens_entrada=100,
            tokens_saida=20,
            tokens_total=120,
            duracao_ms=450,
        ),
    )

    registro = repositorio.obter_execucao_ia(execucao_id)

    assert registro["status"] == "concluida"
    assert registro["configuracao"] == {"limite_fontes": 6}
    assert registro["tokens_total"] == 120
    assert registro["fontes"][0]["chunk_id"].endswith("chunk:1")
    assert repositorio.listar_execucoes_ia()[0]["id"] == execucao_id


def test_audita_erro_e_relatorio_de_avaliacao(tmp_path: Path):
    repositorio = RepositorioSQLite(tmp_path / "tjsp.sqlite3")
    repositorio.inicializar()
    execucao_id = repositorio.iniciar_execucao_ia(
        _pacote(),
        provedor="maritaca",
        modelo="sabia-4",
        configuracao={},
    )
    repositorio.falhar_execucao_ia(execucao_id, "timeout", duracao_ms=1000)
    relatorio = {
        "resumo": {"aprovado": False, "total_casos": 1},
        "casos": [
            {
                "caso_id": "caso-1",
                "pergunta": "Pergunta",
                "aprovado": False,
            }
        ],
    }

    avaliacao_id = repositorio.registrar_avaliacao(
        relatorio,
        dataset="evals/casos.jsonl",
        configuracao={"limite": 6},
    )

    assert avaliacao_id == 1
    assert repositorio.obter_execucao_ia(execucao_id)["status"] == "erro"
    assert repositorio.contagens_auditoria() == {
        "execucoes_ia": 1,
        "fontes_execucao_ia": 1,
        "execucoes_avaliacao": 1,
        "casos_avaliacao": 1,
    }
