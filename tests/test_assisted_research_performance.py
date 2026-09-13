import json
from unittest.mock import MagicMock

from scraping_tjsp.assisted_research import (
    ConfiguracaoPesquisaAssistida,
    PesquisaAssistidaTJSP,
)
from scraping_tjsp.ingestion import ServicoColetaTJSP
from scraping_tjsp.models import Consulta, Decisao, ResultadoPesquisa
from scraping_tjsp.rag import RespostaIA
from scraping_tjsp.research_ranking import (
    buscar_candidatos_tribunais,
)


def _criar_decisao(cd_acordao: str, processo: str) -> Decisao:
    return Decisao(
        processo=processo,
        cd_acordao=cd_acordao,
        cd_foro="0",
        classe="Apelação Cível",
        assunto="Direito Civil",
        relator="Desembargador Teste",
        comarca="São Paulo",
        orgao_julgador="1ª Câmara de Direito Privado",
        data_julgamento="10/01/2026",
        data_publicacao="15/01/2026",
        ementa=f"Ementa do acórdão {cd_acordao} para testes de performance.",
        inteiro_teor_url=f"https://esaj.tjsp.jus.br/cjsg/getArquivo.do?cdAcordao={cd_acordao}",
    )


def test_servico_coleta_pesquisar_indexar_vetores():
    repositorio = MagicMock()
    repositorio.salvar_pesquisa.return_value = 42

    cliente = MagicMock()
    cliente.tribunal = "tjsp"
    cliente.timeout = 30.0
    decisoes = (_criar_decisao("1", "00001"), _criar_decisao("2", "00002"))
    cliente.pesquisar.return_value = ResultadoPesquisa(
        total_disponivel=2,
        paginas_coletadas=1,
        decisoes=decisoes,
    )

    repo_ementas = MagicMock()
    repo_ementas.indexar_decisoes.return_value = 2

    servico = ServicoColetaTJSP(
        repositorio=repositorio,
        cliente=cliente,
        downloader=MagicMock(),
        processador=MagicMock(),
        repositorio_ementas=repo_ementas,
        repositorio_chunks=MagicMock(),
    )

    # 1. indexar_vetores=False (usado em busca rápida de candidatos)
    res_sem_vetores = servico.pesquisar(
        Consulta(pesquisa="prescricao"),
        indexar_vetores=False,
    )
    assert res_sem_vetores["consulta_id"] == 42
    assert res_sem_vetores["ementas_indexadas"] == 0
    assert len(res_sem_vetores["decisoes"]) == 2
    repo_ementas.indexar_decisoes.assert_not_called()

    # 2. indexar_vetores=True (padrão legado)
    res_com_vetores = servico.pesquisar(
        Consulta(pesquisa="prescricao"),
        indexar_vetores=True,
    )
    assert res_com_vetores["consulta_id"] == 42
    assert res_com_vetores["ementas_indexadas"] == 2
    repo_ementas.indexar_decisoes.assert_called_once_with(decisoes)


def test_buscar_candidatos_tribunais_prioridade_e_early_exit():
    servico = MagicMock()
    # Retorna 10 decisões para qualquer consulta
    servico.pesquisar.side_effect = lambda c, **kwargs: {
        "consulta_id": 1,
        "total_disponivel": 10,
        "paginas_coletadas": 1,
        "ementas_indexadas": 0,
        "decisoes": [
            _criar_decisao(
                f"{kwargs.get('tribunal', 'tj')}_{i}", f"proc_{i}"
            ).como_dict()
            for i in range(10)
        ],
    }

    eventos_progresso = []

    def callback(etapa, pct, msg):
        eventos_progresso.append((etapa, pct, msg))

    # Teste de busca multi-tribunal com early exit aos 25 candidatos
    candidatos, executadas, _mapa = buscar_candidatos_tribunais(
        servico,
        consultas=[{"pesquisa": "prescricao", "tipo": "juris"}],
        tribunal="todos",
        max_candidatos=20,
        callback_progresso=callback,
        max_candidatos_coleta=25,
    )

    # Deve ter coletado decisões até bater a meta
    assert len(candidatos) == 20
    assert len(executadas) >= 2
    assert len(eventos_progresso) > 0
    # Confirma que foram reportados acórdãos coletados
    assert any("Coletados" in msg for _, _, msg in eventos_progresso)


def test_pesquisar_stream_emite_eventos_em_tempo_real(tmp_path):
    repo = MagicMock()
    repo.iniciar_execucao_ia.return_value = 1
    repo.salvar_pesquisa.return_value = 10

    servico = MagicMock()
    servico.pesquisar.return_value = {
        "consulta_id": 1,
        "total_disponivel": 2,
        "paginas_coletadas": 1,
        "ementas_indexadas": 0,
        "decisoes": [
            _criar_decisao("501", "00501").como_dict(),
            _criar_decisao("502", "00502").como_dict(),
        ],
    }
    servico.repositorio_ementas = MagicMock()

    # Mock do provedor IA
    resposta_plano = RespostaIA(
        texto=json.dumps(
            {
                "tema": "Prescrição",
                "consultas": [{"pesquisa": "prescricao intercorrente"}],
            }
        ),
        provedor="maritaca",
        modelo="mock-ia",
        tokens_entrada=50,
        tokens_saida=40,
        duracao_ms=100,
    )
    resposta_analise = RespostaIA(
        texto=json.dumps(
            {
                "resultados": [
                    {
                        "cd_acordao": "501",
                        "relevancia": 0.95,
                        "argumento": "Precedente aplicável",
                        "aderencia_fatica": "Fatos idênticos",
                    }
                ]
            }
        ),
        provedor="maritaca",
        modelo="mock-ia",
        tokens_entrada=100,
        tokens_saida=80,
        duracao_ms=200,
    )

    provedor = MagicMock()
    provedor.modelo = "mock-ia"
    provedor.responder.side_effect = [resposta_plano, resposta_analise]

    pesquisa = PesquisaAssistidaTJSP(
        repositorio=repo,
        servico_coleta=servico,
        provedor_factory=lambda mod, tok: provedor,
        configuracao=ConfiguracaoPesquisaAssistida(),
    )

    eventos = list(
        pesquisa.pesquisar_stream(
            "qual o prazo de prescricao?",
            tribunal="tjsp",
        )
    )

    tipos = [e["tipo"] for e in eventos]
    assert "progresso" in tipos
    assert "resultado" in tipos
    # Último evento é o resultado com status concluída
    resultado = eventos[-1]["dados"]
    assert resultado["status"] == "concluida"
    assert len(resultado["processos"]) == 1
    assert resultado["processos"][0]["cd_acordao"] == "501"
