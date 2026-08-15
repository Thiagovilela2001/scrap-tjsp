import json
from pathlib import Path

import pytest

from scraping_tjsp.assisted_research import (
    LimiteCustoPesquisa,
    PesquisaAssistidaTJSP,
    _carregar_json,
)
from scraping_tjsp.models import Decisao
from scraping_tjsp.rag import RespostaIA
from scraping_tjsp.storage import RepositorioSQLite


def _decisao(cd_acordao: str, processo: str) -> Decisao:
    return Decisao(
        processo=processo,
        cd_acordao=cd_acordao,
        cd_foro="0",
        classe="Apelação Cível",
        assunto="ICMS",
        relator="Relator",
        comarca="São Paulo",
        orgao_julgador="Câmara de Direito Público",
        data_julgamento="01/08/2026",
        data_publicacao="02/08/2026",
        ementa=f"ICMS e creditamento no caso {cd_acordao}.",
        inteiro_teor_url=(
            "https://esaj.tjsp.jus.br/cjsg/getArquivo.do"
            f"?casChecked=true&cdAcordao={cd_acordao}&cdForo=0"
        ),
    )


class ServicoColetaFalso:
    def __init__(self) -> None:
        self.consultas = []

    def pesquisar(self, consulta, *, paginas):
        self.consultas.append(consulta.pesquisa)
        indice = len(self.consultas)
        decisoes = (
            [_decisao("101", "1000001-00.2026.8.26.0000")]
            if indice == 1
            else [
                _decisao("101", "1000001-00.2026.8.26.0000"),
                _decisao("202", "1000002-00.2026.8.26.0000"),
            ]
        )
        return {
            "consulta_id": indice,
            "total_disponivel": len(decisoes),
            "paginas_coletadas": 1,
            "ementas_indexadas": len(decisoes),
            "decisoes": [decisao.como_dict() for decisao in decisoes],
        }


class ProvedorFalso:
    modelo = "sabia-4"

    def __init__(self, texto: str) -> None:
        self.texto = texto

    def responder(self, pacote):
        return RespostaIA(
            texto=self.texto,
            provedor="maritaca",
            modelo=self.modelo,
            tokens_entrada=100,
            tokens_saida=50,
            tokens_total=150,
            duracao_ms=10,
        )


class FabricaProvedores:
    def __init__(self, respostas: list[dict]) -> None:
        self.respostas = list(respostas)
        self.chamadas = []

    def __call__(self, modelo, max_output_tokens):
        self.chamadas.append((modelo, max_output_tokens))
        return ProvedorFalso(json.dumps(self.respostas.pop(0), ensure_ascii=False))


def _repositorio(tmp_path: Path) -> RepositorioSQLite:
    repositorio = RepositorioSQLite(tmp_path / "tjsp.sqlite3")
    repositorio.inicializar()
    return repositorio


def test_pede_esclarecimento_sem_consultar_tjsp(tmp_path: Path):
    repositorio = _repositorio(tmp_path)
    coleta = ServicoColetaFalso()
    fabrica = FabricaProvedores(
        [
            {
                "precisa_esclarecimento": True,
                "tema": "ICMS",
                "questoes": ["Qual é a tese específica de ICMS?"],
                "consultas": [],
            }
        ]
    )
    pesquisa = PesquisaAssistidaTJSP(repositorio, coleta, fabrica)

    resultado = pesquisa.pesquisar(
        "Jurisprudência de ICMS para o meu caso.",
        max_custo_brl=1,
    )

    assert resultado["status"] == "precisa_esclarecimento"
    assert resultado["questoes"] == ["Qual é a tese específica de ICMS?"]
    assert coleta.consultas == []
    assert repositorio.contagens_auditoria()["execucoes_ia"] == 1


def test_planeja_busca_ranqueia_processos_e_consolida_consulta(tmp_path: Path):
    repositorio = _repositorio(tmp_path)
    coleta = ServicoColetaFalso()
    fabrica = FabricaProvedores(
        [
            {
                "precisa_esclarecimento": False,
                "tema": "Crédito de ICMS sobre insumos",
                "questoes": [],
                "consultas": [
                    {
                        "pesquisa": "ICMS crédito insumos essenciais",
                        "justificativa": "Localizar creditamento.",
                    },
                    {
                        "pesquisa": "ICMS princípio não cumulatividade insumos",
                        "justificativa": "Localizar fundamento constitucional.",
                    },
                ],
            },
            {
                "resultados": [
                    {
                        "cd_acordao": "202",
                        "relevancia": 0.91,
                        "argumento": "Sustenta o creditamento.",
                        "aderencia_fatica": "Trata de insumos.",
                        "ressalva": "Revisar o inteiro teor.",
                    },
                    {
                        "cd_acordao": "999",
                        "relevancia": 1,
                        "argumento": "ID inventado.",
                    },
                ]
            },
        ]
    )
    pesquisa = PesquisaAssistidaTJSP(repositorio, coleta, fabrica)

    resultado = pesquisa.pesquisar(
        "Busque decisões sobre crédito de ICMS em insumos essenciais.",
        contexto_caso="Indústria paulista teve o crédito glosado.",
        modelo="sabia-4",
        max_custo_brl=1,
    )

    assert resultado["status"] == "concluida"
    assert coleta.consultas == [
        "ICMS crédito insumos essenciais",
        "ICMS princípio não cumulatividade insumos",
    ]
    assert resultado["total_candidatos"] == 2
    assert [item["cd_acordao"] for item in resultado["processos"]] == ["202"]
    assert resultado["processos"][0]["processo"].startswith("1000002")
    assert len(resultado["auditorias_ia"]) == 2
    assert len(repositorio.listar_decisoes_consulta(resultado["consulta_id"])) == 2
    assert resultado["custo"]["chamadas_concluidas"] == 2


def test_teto_baixo_bloqueia_antes_da_ia(tmp_path: Path):
    repositorio = _repositorio(tmp_path)
    fabrica = FabricaProvedores([])
    pesquisa = PesquisaAssistidaTJSP(
        repositorio,
        ServicoColetaFalso(),
        fabrica,
    )

    with pytest.raises(LimiteCustoPesquisa):
        pesquisa.pesquisar(
            "Busque decisões específicas sobre crédito de ICMS.",
            max_custo_brl=0.000001,
        )

    assert fabrica.chamadas == []
    assert repositorio.contagens_auditoria()["execucoes_ia"] == 0


def test_recupera_itens_completos_de_json_truncado():
    resposta = """{
      "resultados": [
        {"cd_acordao": "101", "relevancia": 0.9, "argumento": "Útil."},
        {"cd_acordao": "202", "relevancia": 0.8, "argumento": "Texto interrompido
    """

    dados = _carregar_json(resposta, permitir_resultados_parciais=True)

    assert dados["_resposta_parcial"] is True
    assert dados["resultados"] == [
        {"cd_acordao": "101", "relevancia": 0.9, "argumento": "Útil."}
    ]
