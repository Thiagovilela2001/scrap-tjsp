from pathlib import Path

from fastapi.testclient import TestClient

from scraping_tjsp.api import ConfiguracaoAPI, criar_app
from scraping_tjsp.maritaca import ErroMaritaca
from scraping_tjsp.models import Consulta, Decisao, DocumentoBaixado, ResultadoPesquisa
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


class ServicoTJSPFalso:
    def __init__(self) -> None:
        self.consulta = None
        self.importacao = None

    def pesquisar(self, consulta, *, paginas):
        self.consulta = (consulta, paginas)
        return {
            "consulta_id": 7,
            "total_disponivel": 1,
            "paginas_coletadas": 1,
            "ementas_indexadas": 1,
            "decisoes": [
                {
                    "processo": "1000123-45.2023.8.26.0100",
                    "cd_acordao": "123",
                    "classe": "Apelação Cível",
                    "assunto": "Contratos",
                    "ementa": "Texto da ementa.",
                    "inteiro_teor_url": "https://esaj.tjsp.jus.br/cjsg/getArquivo.do",
                }
            ],
        }

    def importar(self, consulta_id, cd_acordaos):
        self.importacao = (consulta_id, cd_acordaos)
        return {
            "consulta_id": consulta_id,
            "solicitados": len(cd_acordaos),
            "baixados": len(cd_acordaos),
            "reutilizados": 0,
            "processados": len(cd_acordaos),
            "chunks_indexados": 4,
            "erros": [],
        }


class PesquisaAssistidaFalsa:
    def __init__(self) -> None:
        self.chamada = None

    def pesquisar(self, pergunta, **opcoes):
        self.chamada = (pergunta, opcoes)
        return {
            "status": "concluida",
            "tema": "Crédito de ICMS",
            "questoes": [],
            "consultas": [
                {
                    "pesquisa": "ICMS crédito insumos essenciais",
                    "justificativa": "Localizar a tese.",
                    "consulta_id": 8,
                    "total_disponivel": 1,
                    "coletados": 1,
                }
            ],
            "consulta_id": 9,
            "total_candidatos": 1,
            "processos": [
                {
                    "processo": "1000123-45.2023.8.26.0100",
                    "cd_acordao": "123",
                    "ementa": "Texto da ementa.",
                    "inteiro_teor_url": ("https://esaj.tjsp.jus.br/cjsg/getArquivo.do"),
                    "relevancia": 0.91,
                    "argumento": "Possível uso da tese de creditamento.",
                    "aderencia_fatica": "Insumos essenciais.",
                    "ressalva": "Revisar o inteiro teor.",
                }
            ],
            "auditorias_ia": [11, 12],
            "custo": {"custo_padrao_estimado_brl": 0.003},
        }


class AnaliseDocumentalFalsa:
    def __init__(self) -> None:
        self.chamada = None

    def analisar(self, pergunta, cd_acordaos, **opcoes):
        self.chamada = (pergunta, cd_acordaos, opcoes)
        return {
            "status": "concluida",
            "auditoria_id": 13,
            "texto": "Fundamento confirmado no inteiro teor [Fonte 1].",
            "modelo": "sabia-4",
            "tokens_total": 200,
            "duracao_ms": 30,
            "documentos_analisados": ["123"],
            "fontes": [
                {
                    "numero": 1,
                    "id": "acordao:123:pagina:2:chunk:1",
                    "citacao": "Processo X, acórdão 123, p. 2",
                    "url": "/documentos/123",
                    "texto": "Fundamento confirmado.",
                    "score_hibrido": 0.03,
                    "arquivo": "123.pdf",
                }
            ],
            "validacao": {
                "aprovada": True,
                "fontes_citadas": [1],
                "citacoes_invalidas": [],
                "referencias": [],
                "referencias_nao_verificadas": [],
            },
            "custo": {"custo_padrao_estimado_brl": 0.004},
        }


def _cliente(
    tmp_path: Path,
    *,
    busca=None,
    provedor_factory=None,
    servico_tjsp=None,
    pesquisa_assistida=None,
    analise_documental=None,
    max_custo_brl: float = 1.0,
) -> tuple[TestClient, RepositorioSQLite]:
    repositorio = RepositorioSQLite(tmp_path / "tjsp.sqlite3")
    app = criar_app(
        configuracao=ConfiguracaoAPI(
            sqlite_path=tmp_path / "tjsp.sqlite3",
            chroma_path=tmp_path / "chroma",
            max_custo_brl=max_custo_brl,
            max_output_tokens=2_000,
            diretorio_pdfs=tmp_path / "pdfs",
        ),
        repositorio=repositorio,
        busca=busca or BuscaFalsa(),
        provedor_factory=provedor_factory or (lambda modelo, tokens: ProvedorFalso()),
        servico_tjsp=servico_tjsp or ServicoTJSPFalso(),
        pesquisa_assistida=pesquisa_assistida,
        analise_documental=analise_documental,
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
    assert saude.json()["chunks_indexados"] == 0
    assert resposta.status_code == 200
    assert resposta.json()["total"] == 1
    assert resposta.json()["resultados"][0]["id"].startswith("acordao:123")
    assert busca.chamada["texto"] == "dano moral"
    assert busca.chamada["filtros"] == {"cd_acordao": "123"}


def test_raiz_entrega_interface_e_assets(tmp_path: Path):
    cliente, _ = _cliente(tmp_path)

    resposta = cliente.get("/")
    estilos = cliente.get("/assets/styles.css")
    script = cliente.get("/assets/app.js")

    assert resposta.status_code == 200
    assert "Pesquisa jurisprudencial" in resposta.text
    assert 'name="contexto_caso"' in resposta.text
    assert 'aria-label="Etapas da pesquisa"' in resposta.text
    assert 'data-etapa="analise"' in resposta.text
    assert 'id="selecionar-recomendados"' in resposta.text
    assert 'id="limpar-selecao"' in resposta.text
    assert "data-modo" not in resposta.text
    assert estilos.status_code == 200
    assert "--cor-tinta" in estilos.text
    assert ".fluxo-iniciado .apresentacao" in estilos.text
    assert ".detalhes-resultado" in estilos.text
    assert script.status_code == 200
    assert 'fetch("/saude")' in script.text
    assert "criarEntrevistaEsclarecimentos" in script.text
    assert "criarDetalhesResultado" in script.text
    assert "selecionarRecomendados" in script.text
    assert "[data-modo]" not in script.text
    assert "limitada pelo servidor a R$ 0,20" not in script.text
    assert "max_custo_analise_documental_brl" in script.text
    assert "innerHTML" not in script.text


def test_pesquisa_e_importa_acordaos_do_tjsp(tmp_path: Path):
    servico = ServicoTJSPFalso()
    cliente, _ = _cliente(tmp_path, servico_tjsp=servico)

    pesquisa = cliente.post(
        "/tjsp/pesquisar",
        json={"pesquisa": "responsabilidade civil", "paginas": 1},
    )
    importacao = cliente.post(
        "/tjsp/importar",
        json={"consulta_id": 7, "cd_acordaos": ["123"]},
    )

    assert pesquisa.status_code == 200
    assert pesquisa.json()["decisoes"][0]["cd_acordao"] == "123"
    assert servico.consulta[0].pesquisa == "responsabilidade civil"
    assert servico.consulta[1] == 1
    assert importacao.status_code == 200
    assert importacao.json()["chunks_indexados"] == 4
    assert servico.importacao == (7, ["123"])


def test_gerar_minuta_de_peticao(tmp_path: Path):
    cliente, _ = _cliente(tmp_path)

    resposta = cliente.post(
        "/tjsp/gerar-minuta",
        json={
            "tema": "Dano moral por negativação indevida",
            "pergunta": "Meu cliente foi negativado indevidamente por dívida paga.",
            "acordaos_selecionados": [
                {
                    "processo": "1000000-00.2023.8.26.0100",
                    "cd_acordao": "12345",
                    "relator": "Des. Carlos Silva",
                    "orgao_julgador": "1ª Câmara de Direito Privado",
                    "ementa": "Dano moral configurado in re ipsa.",
                    "argumento": "A jurisprudência dispensa prova do prejuízo.",
                }
            ],
            "instrucao": "Pedir tutela antecipada",
        },
    )

    assert resposta.status_code == 200
    dados = resposta.json()
    assert "minuta" in dados
    assert "MINUTA DE FUNDAMENTAÇÃO" in dados["minuta"]
    assert "1000000-00.2023.8.26.0100" in dados["minuta"]
    assert dados["acordaos_utilizados"] == 1


def test_abre_pdf_local_pelo_codigo_do_acordao(tmp_path: Path):
    cliente, repositorio = _cliente(tmp_path)
    decisao = Decisao(
        processo="1000123-45.2023.8.26.0100",
        cd_acordao="123",
        cd_foro="0",
        classe="Apelação Cível",
        assunto="Contratos",
        relator="Relator",
        comarca="São Paulo",
        orgao_julgador="1ª Câmara",
        data_julgamento="01/08/2026",
        data_publicacao="02/08/2026",
        ementa="Texto.",
        inteiro_teor_url="https://esaj.tjsp.jus.br/cjsg/getArquivo.do",
    )
    repositorio.salvar_pesquisa(
        Consulta(pesquisa="contrato"),
        ResultadoPesquisa(1, 1, (decisao,)),
    )
    caminho_pdf = tmp_path / "pdfs" / "123.pdf"
    caminho_pdf.parent.mkdir()
    caminho_pdf.write_bytes(b"%PDF-conteudo-de-teste")
    repositorio.registrar_documento(
        DocumentoBaixado(
            cd_acordao="123",
            url_origem=decisao.inteiro_teor_url,
            caminho_local=str(caminho_pdf),
            mime_type="application/pdf",
            tamanho_bytes=caminho_pdf.stat().st_size,
            sha256="a" * 64,
        )
    )

    resposta = cliente.get("/documentos/123")

    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == "application/pdf"
    assert resposta.content.startswith(b"%PDF-")



def test_pesquisa_assistida_planeja_busca_no_tjsp(tmp_path: Path):
    pesquisa = PesquisaAssistidaFalsa()
    cliente, _ = _cliente(tmp_path, pesquisa_assistida=pesquisa)

    resposta = cliente.post(
        "/tjsp/pesquisa-assistida",
        json={
            "pergunta": "Encontre jurisprudência sobre crédito de ICMS.",
            "contexto_caso": "Crédito glosado sobre insumos essenciais.",
            "max_custo_brl": 0.10,
        },
    )

    assert resposta.status_code == 200
    assert resposta.json()["processos"][0]["cd_acordao"] == "123"
    assert pesquisa.chamada[0].startswith("Encontre jurisprudência")
    assert pesquisa.chamada[1]["contexto_caso"].startswith("Crédito glosado")
    assert pesquisa.chamada[1]["max_custo_brl"] == 0.10


def test_analisa_inteiros_teores_importados_com_validacao(tmp_path: Path):
    analise = AnaliseDocumentalFalsa()
    cliente, _ = _cliente(tmp_path, analise_documental=analise)

    resposta = cliente.post(
        "/tjsp/analisar-documentos",
        json={
            "pergunta": "Quais fundamentos podem ser utilizados?",
            "contexto_caso": "Consumidor questiona a cobrança.",
            "cd_acordaos": ["123"],
            "max_custo_brl": 0.10,
        },
    )

    assert resposta.status_code == 200
    assert resposta.json()["validacao"]["aprovada"] is True
    assert resposta.json()["fontes"][0]["arquivo"] == "123.pdf"
    assert analise.chamada[1] == ["123"]
    assert analise.chamada[2]["contexto_caso"].startswith("Consumidor")


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
