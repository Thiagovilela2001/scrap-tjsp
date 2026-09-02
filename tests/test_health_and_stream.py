from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from scraping_tjsp.api import ConfiguracaoAPI, criar_app
from scraping_tjsp.assisted_research import PesquisaAssistidaTJSP
from scraping_tjsp.models import Decisao
from scraping_tjsp.rag import RespostaIA
from scraping_tjsp.storage import RepositorioSQLite


def test_saude_diagnosticos(tmp_path: Path) -> None:
    config = ConfiguracaoAPI(
        sqlite_path=tmp_path / "app.sqlite3",
        chroma_path=tmp_path / "chroma",
        diretorio_pdfs=tmp_path / "pdfs",
    )
    repo = RepositorioSQLite(config.sqlite_path)
    repo.inicializar()

    mock_busca = MagicMock()
    mock_chunks = MagicMock()
    mock_chunks.colecao.count.return_value = 5

    app = criar_app(
        configuracao=config,
        repositorio=repo,
        busca=mock_busca,
        repositorio_chunks=mock_chunks,
    )
    cliente = TestClient(app)

    resposta = cliente.get("/saude")
    assert resposta.status_code == 200
    dados = resposta.json()

    assert dados["status"] in ("ok", "atencao")
    assert "diagnosticos" in dados
    diag = dados["diagnosticos"]
    assert "sqlite" in diag
    assert "chroma" in diag
    assert "maritaca" in diag
    assert "tesseract_ocr" in diag
    assert diag["sqlite"]["status"] == "ok"
    assert diag["chroma"]["status"] == "ok"


def test_pesquisa_assistida_progresso_callback() -> None:
    repo = MagicMock()
    repo.salvar_pesquisa.return_value = 1
    servico = MagicMock()
    decisao = Decisao(
        cd_acordao="1001",
        cd_foro="0001",
        processo="0001-2026",
        classe="Apelação",
        assunto="Dano",
        relator="Desembargador",
        comarca="São Paulo",
        orgao_julgador="1ª Câmara",
        data_julgamento="10/08/2026",
        data_publicacao="12/08/2026",
        ementa="Ementa exemplo responsabilidade civil",
        inteiro_teor_url="https://esaj.tjsp.jus.br/cjsg/getArquivo.do?cdAcordao=1001",
    )
    servico.pesquisar.return_value = {
        "consulta_id": 1,
        "total_disponivel": 1,
        "paginas_coletadas": 1,
        "decisoes": [decisao.como_dict()],
    }

    provedor_plano = MagicMock()
    provedor_plano.responder.return_value = RespostaIA(
        texto=json.dumps(
            {
                "precisa_esclarecimento": False,
                "questoes": [],
                "tema": "Dano moral",
                "consultas": [{"pesquisa": "dano moral atraso voo", "justificativa": "tese"}],
            }
        ),
        provedor="maritaca",
        modelo="sabia-4",
        tokens_entrada=10,
        tokens_saida=10,
        duracao_ms=50,
    )

    provedor_analise = MagicMock()
    provedor_analise.responder.return_value = RespostaIA(
        texto=json.dumps(
            {
                "resultados": [
                    {
                        "cd_acordao": "1001",
                        "relevancia": 0.9,
                        "argumento": "Atraso enseja indenização",
                        "aderencia_fatica": "Caso idêntico",
                        "ressalva": "Revisar acórdão",
                    }
                ]
            }
        ),
        provedor="maritaca",
        modelo="sabia-4",
        tokens_entrada=10,
        tokens_saida=10,
        duracao_ms=50,
    )

    def factory(modelo, tokens):
        return provedor_plano if tokens <= 500 else provedor_analise

    pesquisa = PesquisaAssistidaTJSP(
        repositorio=repo,
        servico_coleta=servico,
        provedor_factory=factory,
    )

    etapas = []

    def callback(etapa: str, progresso: int, mensagem: str) -> None:
        etapas.append((etapa, progresso))

    resultado = pesquisa.pesquisar(
        "Indenização por atraso de voo internacional",
        callback_progresso=callback,
    )

    assert resultado["status"] == "concluida"
    assert len(etapas) >= 3
    assert any(e[0] == "planejamento" for e in etapas)
    assert any(e[0] == "coleta" for e in etapas)
    assert any(e[0] == "analise" for e in etapas)


def test_pesquisa_assistida_stream_endpoint(tmp_path: Path) -> None:
    config = ConfiguracaoAPI(
        sqlite_path=tmp_path / "app.sqlite3",
        chroma_path=tmp_path / "chroma",
        diretorio_pdfs=tmp_path / "pdfs",
    )
    repo = RepositorioSQLite(config.sqlite_path)
    repo.inicializar()

    mock_pesquisa = MagicMock()
    mock_pesquisa.pesquisar_stream.return_value = [
        {"tipo": "progresso", "etapa": "planejamento", "progresso": 15, "mensagem": "Planejando..."},
        {"tipo": "resultado", "dados": {"status": "concluida", "tema": "Dano", "processos": []}},
    ]

    app = criar_app(
        configuracao=config,
        repositorio=repo,
        pesquisa_assistida=mock_pesquisa,
    )
    cliente = TestClient(app)

    resposta = cliente.post(
        "/tjsp/pesquisa-assistida/stream",
        json={"pergunta": "Pergunta de teste para SSE stream"},
    )
    assert resposta.status_code == 200
    assert "text/event-stream" in resposta.headers.get("content-type", "")
    conteudo = resposta.text
    assert "data: " in conteudo
    assert "planejamento" in conteudo
