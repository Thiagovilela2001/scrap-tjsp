from pathlib import Path

from fastapi.testclient import TestClient

from scraping_tjsp.api import ConfiguracaoAPI, criar_app
from scraping_tjsp.maritaca import ErroMaritaca
from scraping_tjsp.rag import RespostaIA
from scraping_tjsp.search import ResultadoBuscaHibrida
from scraping_tjsp.storage import RepositorioSQLite


class BuscaFalsa:
    def __init__(self, *, com_resultado: bool = True) -> None:
        self.com_resultado = com_resultado
        self.chamada = None

    def buscar(self, texto, *, limite, filtros, candidatos=None):
        self.chamada = {
            "texto": texto,
            "limite": limite,
            "filtros": filtros,
            "candidatos": candidatos,
        }
        if not self.com_resultado:
            return []
        return [
            ResultadoBuscaHibrida(
                id="acordao:123:pagina:2:chunk:1",
                texto="Dano moral reconhecido pelo acórdão.",
                metadata={
                    "cd_acordao": "123",
                    "citacao": "Processo X, acórdão 123, p. 2",
                    "inteiro_teor_url": "https://esaj.tjsp.jus.br/cjsg/getArquivo.do",
                },
                score_hibrido=0.03,
                origens=("semantica", "lexical"),
                rank_semantico=1,
                rank_lexical=1,
            )
        ]


class ProvedorFalso:
    modelo = "sabia-4"

    def responder(self, pacote):
        return RespostaIA(
            texto="O dano moral foi reconhecido [Fonte 1].",
            provedor="maritaca",
            modelo=self.modelo,
            resposta_id="resp-api-1",
            tokens_entrada=100,
            tokens_saida=20,
            tokens_total=120,
            duracao_ms=50,
        )


class ProvedorComErro(ProvedorFalso):
    def responder(self, pacote):
        raise ErroMaritaca("Falha simulada.", duracao_ms=25)


def _cliente(
    tmp_path: Path,
    *,
    busca=None,
    provedor_factory=None,
    max_custo_brl: float = 1.0,
) -> tuple[TestClient, RepositorioSQLite]:
    repositorio = RepositorioSQLite(tmp_path / "tjsp.sqlite3")
    app = criar_app(
        configuracao=ConfiguracaoAPI(
            sqlite_path=tmp_path / "tjsp.sqlite3",
            chroma_path=tmp_path / "chroma",
            max_custo_brl=max_custo_brl,
            max_output_tokens=2_000,
        ),
        repositorio=repositorio,
        busca=busca or BuscaFalsa(),
        provedor_factory=provedor_factory or (lambda modelo, tokens: ProvedorFalso()),
    )
    return TestClient(app), repositorio


def test_saude_e_busca_hibrida(tmp_path: Path):
    busca = BuscaFalsa()
    cliente, _ = _cliente(tmp_path, busca=busca)

    saude = cliente.get("/saude")
    resposta = cliente.post(
        "/buscar",
        json={
            "pergunta": " dano moral ",
            "limite": 5,
            "filtros": {"cd_acordao": "123"},
        },
    )

    assert saude.json()["status"] == "ok"
    assert resposta.status_code == 200
    assert resposta.json()["total"] == 1
    assert resposta.json()["resultados"][0]["id"].startswith("acordao:123")
    assert busca.chamada["texto"] == "dano moral"
    assert busca.chamada["filtros"] == {"cd_acordao": "123"}


def test_raiz_redireciona_para_documentacao(tmp_path: Path):
    cliente, _ = _cliente(tmp_path)

    resposta = cliente.get("/", follow_redirects=False)

    assert resposta.status_code == 307
    assert resposta.headers["location"] == "/docs"


def test_pergunta_responde_com_fontes_custo_e_auditoria(tmp_path: Path):
    cliente, repositorio = _cliente(tmp_path)

    resposta = cliente.post(
        "/perguntar",
        json={
            "pergunta": "Qual foi o resultado?",
            "max_output_tokens": 800,
            "max_custo_brl": 0.10,
        },
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["texto"].endswith("[Fonte 1].")
    assert corpo["fontes"][0]["id"].startswith("acordao:123")
    assert corpo["custo"]["custo_padrao_estimado_brl"] > 0
    auditoria = repositorio.obter_execucao_ia(corpo["auditoria_id"])
    assert auditoria["status"] == "concluida"
    assert auditoria["tokens_total"] == 120


def test_teto_de_custo_bloqueia_antes_do_provedor(tmp_path: Path):
    chamadas = []

    def criar_provedor(modelo, tokens):
        chamadas.append((modelo, tokens))
        return ProvedorFalso()

    cliente, repositorio = _cliente(
        tmp_path,
        provedor_factory=criar_provedor,
    )

    resposta = cliente.post(
        "/perguntar",
        json={
            "pergunta": "Qual foi o resultado?",
            "max_output_tokens": 800,
            "max_custo_brl": 0.000001,
        },
    )

    assert resposta.status_code == 422
    assert "excede" in resposta.json()["detail"]["erro"]
    assert chamadas == []
    assert repositorio.listar_execucoes_ia() == []


def test_cliente_nao_pode_superar_limites_do_servidor(tmp_path: Path):
    chamadas = []
    cliente, _ = _cliente(
        tmp_path,
        provedor_factory=lambda modelo, tokens: chamadas.append(1),
        max_custo_brl=0.10,
    )

    custo = cliente.post(
        "/perguntar",
        json={"pergunta": "Pergunta.", "max_custo_brl": 0.11},
    )
    tokens = cliente.post(
        "/perguntar",
        json={"pergunta": "Pergunta.", "max_output_tokens": 2_001},
    )

    assert custo.status_code == 422
    assert "limite do servidor" in custo.json()["detail"]
    assert tokens.status_code == 422
    assert "limite do servidor" in tokens.json()["detail"]
    assert chamadas == []


def test_sem_fontes_nao_chama_ia(tmp_path: Path):
    chamadas = []
    cliente, repositorio = _cliente(
        tmp_path,
        busca=BuscaFalsa(com_resultado=False),
        provedor_factory=lambda modelo, tokens: chamadas.append(1),
    )

    resposta = cliente.post(
        "/perguntar",
        json={"pergunta": "Pergunta sem resultados."},
    )

    assert resposta.status_code == 422
    assert "não realizada" in resposta.json()["detail"]
    assert chamadas == []
    assert repositorio.listar_execucoes_ia() == []


def test_chave_ausente_retorna_servico_indisponivel(tmp_path: Path):
    def falhar_configuracao(modelo, tokens):
        raise ErroMaritaca("MARITACA_API_KEY não configurada.")

    cliente, _ = _cliente(tmp_path, provedor_factory=falhar_configuracao)

    resposta = cliente.post(
        "/perguntar",
        json={"pergunta": "Qual foi o resultado?"},
    )

    assert resposta.status_code == 503
    assert "MARITACA_API_KEY" in resposta.json()["detail"]


def test_falha_do_provedor_fica_auditada(tmp_path: Path):
    cliente, repositorio = _cliente(
        tmp_path,
        provedor_factory=lambda modelo, tokens: ProvedorComErro(),
    )

    resposta = cliente.post(
        "/perguntar",
        json={"pergunta": "Qual foi o resultado?"},
    )

    assert resposta.status_code == 502
    auditorias = repositorio.listar_execucoes_ia()
    assert auditorias[0]["status"] == "erro"
    assert auditorias[0]["duracao_ms"] == 25


def test_auditoria_inexistente_retorna_404(tmp_path: Path):
    cliente, _ = _cliente(tmp_path)

    resposta = cliente.get("/auditorias/999")

    assert resposta.status_code == 404
