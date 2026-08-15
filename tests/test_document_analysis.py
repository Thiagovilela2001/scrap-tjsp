from scraping_tjsp.document_analysis import AnaliseDocumentalTJSP
from scraping_tjsp.rag import RespostaIA
from scraping_tjsp.search import ResultadoBuscaHibrida


class BuscaFalsa:
    def __init__(self) -> None:
        self.filtros = []

    def buscar(self, texto, *, limite, candidatos, filtros):
        self.filtros.append(filtros)
        cd_acordao = filtros["cd_acordao"]
        return [
            ResultadoBuscaHibrida(
                id=f"acordao:{cd_acordao}:pagina:7:chunk:1",
                texto="O Tema 176 afasta a cobrança sobre energia não consumida.",
                metadata={
                    "cd_acordao": cd_acordao,
                    "processo": "1035947-80.2016.8.26.0053",
                    "pagina": 7,
                    "arquivo": f"{cd_acordao}.pdf",
                    "citacao": (
                        "Processo 1035947-80.2016.8.26.0053, "
                        f"acórdão {cd_acordao}, p. 7"
                    ),
                },
                score_hibrido=0.03,
                origens=("semantica", "lexical"),
            )
        ]


class RepositorioFalso:
    def __init__(self) -> None:
        self.inicio = None
        self.conclusao = None

    def iniciar_execucao_ia(self, pacote, **dados):
        self.inicio = (pacote, dados)
        return 31

    def concluir_execucao_ia(self, execucao_id, resposta):
        self.conclusao = (execucao_id, resposta)

    def falhar_execucao_ia(self, *args, **kwargs):
        raise AssertionError("Não deveria falhar.")


class ProvedorFalso:
    modelo = "sabia-4"

    def responder(self, pacote):
        return RespostaIA(
            texto=(
                "Síntese: o processo 1035947-80.2016.8.26.0053, acórdão "
                "19200575, aplica o Tema 176 na página 7 [Fonte 1]."
            ),
            provedor="maritaca",
            modelo=self.modelo,
            tokens_entrada=300,
            tokens_saida=80,
            tokens_total=380,
        )


def test_recupera_pdf_por_acordao_analisa_e_valida_fontes():
    repositorio = RepositorioFalso()
    busca = BuscaFalsa()
    analise = AnaliseDocumentalTJSP(
        repositorio,
        busca,
        lambda modelo, tokens: ProvedorFalso(),
    )

    resultado = analise.analisar(
        "Quais argumentos afastam a cobrança?",
        ["19200575"],
        contexto_caso="Energia contratada e não consumida.",
        max_custo_brl=1,
    )

    assert resultado["status"] == "concluida"
    assert resultado["validacao"]["aprovada"] is True
    assert resultado["fontes"][0]["arquivo"] == "19200575.pdf"
    assert resultado["fontes"][0]["url"] == "/documentos/19200575"
    assert resultado["documentos_analisados"] == ["19200575"]
    assert busca.filtros == [{"cd_acordao": "19200575"}]
    assert repositorio.conclusao[0] == 31


def test_nao_chama_ia_sem_chunks_importados():
    busca = BuscaFalsa()
    busca.buscar = lambda *args, **kwargs: []
    chamadas = []
    analise = AnaliseDocumentalTJSP(
        RepositorioFalso(),
        busca,
        lambda modelo, tokens: chamadas.append(1),
    )

    try:
        analise.analisar(
            "Analise os fundamentos.",
            ["19200575"],
            max_custo_brl=1,
        )
    except ValueError as exc:
        assert "Importe e processe" in str(exc)
    else:
        raise AssertionError("Era esperada falha sem chunks.")

    assert chamadas == []
