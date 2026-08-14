import pytest

from scraping_tjsp.models import Consulta


def test_exige_algum_filtro():
    with pytest.raises(ValueError, match="pelo menos um filtro"):
        Consulta().validar()


def test_limita_intervalo_a_366_dias():
    consulta = Consulta(
        pesquisa="contrato",
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="02/01/2025",
    )
    with pytest.raises(ValueError, match="366 dias"):
        consulta.validar()


def test_aceita_intervalo_curto():
    Consulta(
        pesquisa="contrato",
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/01/2024",
    ).validar()


def test_recusa_tipo_de_decisao_desconhecido():
    with pytest.raises(ValueError, match="Tipo de decisão inválido"):
        Consulta(pesquisa="contrato", tipo_decisao="sentenca").validar()
