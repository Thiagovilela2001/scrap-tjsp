import pytest

from scraping_tjsp.client import TJSPClient, tribunais_ativos

TODOS_27_TJS = (
    "tjac",
    "tjal",
    "tjap",
    "tjam",
    "tjba",
    "tjce",
    "tjdft",
    "tjes",
    "tjgo",
    "tjma",
    "tjmt",
    "tjms",
    "tjmg",
    "tjpa",
    "tjpb",
    "tjpr",
    "tjpe",
    "tjpi",
    "tjrj",
    "tjrn",
    "tjrs",
    "tjro",
    "tjrr",
    "tjsc",
    "tjsp",
    "tjse",
    "tjto",
)


def test_lista_somente_adaptadores_esaj_ativos():
    assert tribunais_ativos(adaptador="esaj_cjsg") == (
        "tjsp",
        "tjms",
        "tjam",
        "tjac",
    )


def test_lista_todos_os_tribunais_ativos():
    ativos = tribunais_ativos()
    assert "tjsp" in ativos
    assert "tjpr" in ativos
    assert "datajud_tjrj" in ativos
    assert "datajud_tjmg" in ativos
    assert "datajud_tjrs" in ativos
    for tj in TODOS_27_TJS:
        assert tj in ativos, f"{tj} não encontrado entre os tribunais ativos"
    assert len(ativos) >= 27


def test_lista_somente_adaptadores_datajud_ativos():
    datajud_ativos = tribunais_ativos(adaptador="datajud")
    assert "datajud_tjsp" in datajud_ativos
    assert "datajud_tjrj" in datajud_ativos
    assert "datajud_tjmg" in datajud_ativos
    assert "datajud_tjrs" in datajud_ativos
    assert "datajud_tjba" in datajud_ativos
    assert "datajud_tjdft" in datajud_ativos
    assert "datajud_trf1" in datajud_ativos
    assert len(datajud_ativos) >= 27


def test_cliente_aceita_qualquer_tribunal_datajud_dinamicamente():
    cliente = TJSPClient(tribunal="datajud_tjrj")
    assert cliente.adapter.sigla_tribunal == "tjrj"

    # Tribunal arbitrário que não estava pré-definido
    cliente_novo = TJSPClient(tribunal="datajud_tribunalextra")
    assert cliente_novo.adapter.sigla_tribunal == "tribunalextra"
    assert cliente_novo.adapter.indice_tribunal == "api_publica_tribunalextra"


def test_cliente_todos_os_27_tjs_sao_inicializaveis():
    for tj in TODOS_27_TJS:
        cliente = TJSPClient(tribunal=tj)
        assert cliente.tribunal == tj
        if tj in ("tjsp", "tjms", "tjam", "tjac"):
            assert cliente.adapter.__class__.__name__ == "ESAJCJSGAdapter"
        elif tj == "tjpr":
            assert cliente.adapter.__class__.__name__ == "TJPRAdapter"
        else:
            assert cliente.adapter.__class__.__name__ == "DataJudAdapter"
            assert cliente.adapter.sigla_tribunal == tj


def test_cliente_recusa_tribunal_desconhecido():
    with pytest.raises(ValueError, match="Tribunal não configurado"):
        TJSPClient(tribunal="tjxx")


def test_cliente_explica_por_que_tribunal_esta_inativo(monkeypatch):
    from scraping_tjsp.client import TRIBUNAIS_CONFIG

    monkeypatch.setitem(
        TRIBUNAIS_CONFIG,
        "tjinativo",
        {
            "sigla": "TJINATIVO",
            "ativo": False,
            "motivo_inativo": "Portal fora do ar para manutenção.",
        },
    )
    with pytest.raises(ValueError, match="fora do ar"):
        TJSPClient(tribunal="tjinativo")


def test_cliente_aceita_endpoint_customizado_para_novo_esaj():
    cliente = TJSPClient(
        tribunal="tjxx",
        base_url="https://esaj.tjxx.jus.br/cjsg",
    )

    assert cliente.adapter.url("getArquivo.do") == (
        "https://esaj.tjxx.jus.br/cjsg/getArquivo.do"
    )


def test_tribunais_superiores_ativos():
    ativos = tribunais_ativos()
    for sup in ("stj", "tst", "tse", "stm"):
        assert sup in ativos, f"{sup} deve estar ativo"
        cliente = TJSPClient(tribunal=sup)
        assert cliente.adapter.__class__.__name__ == "DataJudAdapter"
        assert cliente.adapter.sigla_tribunal == sup
        assert cliente.adapter.indice_tribunal == f"api_publica_{sup}"

    # STF com status ativo e adaptador STFAdapter
    assert "stf" in ativos
    cliente_stf = TJSPClient(tribunal="stf")
    assert cliente_stf.adapter.__class__.__name__ == "STFAdapter"
