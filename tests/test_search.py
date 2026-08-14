from scraping_tjsp.search import BuscaHibrida


class SQLiteFalso:
    def __init__(self):
        self.filtros = None

    def buscar_chunks_lexical(self, texto, *, limite, filtros):
        self.filtros = filtros
        return [
            {
                "id": "acordao:1:pagina:2:chunk:1",
                "documento": "Dano moral configurado.",
                "metadata": {"cd_acordao": "1", "pagina": 2},
                "score_bm25": -1.5,
            },
            {
                "id": "acordao:2:pagina:1:chunk:1",
                "documento": "Outro resultado lexical.",
                "metadata": {"cd_acordao": "2", "pagina": 1},
                "score_bm25": -0.8,
            },
        ]


class ChromaFalso:
    def __init__(self):
        self.filtros = None

    def buscar(self, texto, *, limite, filtros):
        self.filtros = filtros
        return [
            {
                "id": "acordao:1:pagina:2:chunk:1",
                "documento": "Dano moral configurado.",
                "metadata": {
                    "cd_acordao": "1",
                    "pagina": 2,
                    "citacao": "Processo X, acórdão 1, p. 2",
                },
                "distancia": 0.1,
            },
            {
                "id": "acordao:3:pagina:4:chunk:1",
                "documento": "Resultado apenas semântico.",
                "metadata": {"cd_acordao": "3", "pagina": 4},
                "distancia": 0.2,
            },
        ]


def test_funde_rankings_com_rrf_e_deduplica():
    sqlite = SQLiteFalso()
    chroma = ChromaFalso()
    busca = BuscaHibrida(sqlite, chroma)

    resultados = busca.buscar(
        "dano moral",
        limite=3,
        filtros={"cd_acordao": "1", "pagina": 2},
    )

    primeiro = resultados[0]
    assert primeiro.id == "acordao:1:pagina:2:chunk:1"
    assert primeiro.origens == ("semantica", "lexical")
    assert primeiro.rank_semantico == 1
    assert primeiro.rank_lexical == 1
    assert primeiro.score_hibrido == 2 / 61
    assert sqlite.filtros == {"cd_acordao": "1", "pagina": 2}
    assert chroma.filtros == {"$and": [{"cd_acordao": "1"}, {"pagina": 2}]}
