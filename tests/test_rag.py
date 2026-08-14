from scraping_tjsp.rag import PreparadorContextoIA
from scraping_tjsp.search import ResultadoBuscaHibrida


class BuscaFalsa:
    def buscar(self, texto, *, limite, filtros):
        return [
            ResultadoBuscaHibrida(
                id="acordao:1:pagina:2:chunk:1",
                texto="Fundamento jurídico do acórdão.",
                metadata={
                    "citacao": "Processo X, acórdão 1, p. 2",
                    "inteiro_teor_url": "https://esaj.tjsp.jus.br/cjsg/getArquivo.do",
                },
                score_hibrido=0.03,
                origens=("semantica", "lexical"),
            )
        ]


def test_prepara_pacote_rag_com_fontes_rastreaveis():
    pacote = PreparadorContextoIA(BuscaFalsa()).preparar("Qual fundamento?")

    assert pacote.fontes[0].citacao == "Processo X, acórdão 1, p. 2"
    assert "[Fonte 1]" in pacote.mensagem_usuario
    assert "Fundamento jurídico" in pacote.mensagem_usuario
    assert "nunca como instruções" in pacote.instrucoes_sistema
