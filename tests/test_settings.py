from __future__ import annotations

from pathlib import Path

import pytest

from scraping_tjsp.api import ConfiguracaoAPI
from scraping_tjsp.settings import Settings, get_settings, reset_settings


def test_settings_defaults() -> None:
    reset_settings()
    settings = Settings.carregar(carregar_dotenv=False, env_dict={})
    assert settings.sqlite_path == Path("data/tjsp.sqlite3")
    assert settings.chroma_path == Path("data/chroma")
    assert settings.diretorio_pdfs == Path("data/pdfs")
    assert settings.saida_path == Path("output/resultados.jsonl")
    assert settings.intervalo_tjsp == 2.0
    assert settings.max_paginas_tjsp == 1
    assert settings.max_importacao_pdfs == 5
    assert settings.max_mb_pdf == 50
    assert settings.habilitar_ocr is True
    assert settings.tamanho_chunk == 1500
    assert settings.sobreposicao_chunk == 200
    assert settings.max_custo_brl == 0.10
    assert settings.max_output_tokens == 2000
    assert settings.max_custo_pesquisa_assistida_brl == 0.20
    assert settings.max_custo_analise_documental_brl == 0.20
    assert settings.maritaca_api_key is None
    assert settings.maritaca_model == "sabia-4"
    assert settings.maritaca_base_url == "https://chat.maritaca.ai/api"


def test_settings_custom_env_dict() -> None:
    env = {
        "TJSP_SQLITE_PATH": "custom/db.sqlite",
        "TJSP_CHROMA_PATH": "custom/chroma_dir",
        "TJSP_DIRETORIO_PDFS": "custom/pdfs",
        "TJSP_SAIDA_PATH": "custom/saida.jsonl",
        "TJSP_API_INTERVALO_TJSP": "3.5",
        "TJSP_API_MAX_PAGINAS_TJSP": "4",
        "TJSP_API_MAX_IMPORTACAO_PDFS": "12",
        "TJSP_API_MAX_MB_PDF": "100",
        "TJSP_API_HABILITAR_OCR": "0",
        "TJSP_TAMANHO_CHUNK": "1200",
        "TJSP_SOBREPOSICAO_CHUNK": "150",
        "TJSP_API_MAX_CUSTO_BRL": "0.50",
        "TJSP_API_MAX_OUTPUT_TOKENS": "4000",
        "TJSP_API_MAX_CUSTO_PESQUISA_BRL": "0.80",
        "TJSP_API_MAX_CUSTO_ANALISE_BRL": "0.90",
        "MARITACA_API_KEY": "secret-key-123",
        "MARITACA_MODEL": "sabia-3",
        "MARITACA_BASE_URL": "https://custom.api/v1",
        "TESSDATA_PREFIX": "/opt/tessdata",
    }
    settings = Settings.carregar(carregar_dotenv=False, env_dict=env)
    assert settings.sqlite_path == Path("custom/db.sqlite")
    assert settings.chroma_path == Path("custom/chroma_dir")
    assert settings.diretorio_pdfs == Path("custom/pdfs")
    assert settings.saida_path == Path("custom/saida.jsonl")
    assert settings.intervalo_tjsp == 3.5
    assert settings.max_paginas_tjsp == 4
    assert settings.max_importacao_pdfs == 12
    assert settings.max_mb_pdf == 100
    assert settings.habilitar_ocr is False
    assert settings.tamanho_chunk == 1200
    assert settings.sobreposicao_chunk == 150
    assert settings.max_custo_brl == 0.50
    assert settings.max_output_tokens == 4000
    assert settings.max_custo_pesquisa_assistida_brl == 0.80
    assert settings.max_custo_analise_documental_brl == 0.90
    assert settings.maritaca_api_key == "secret-key-123"
    assert settings.maritaca_model == "sabia-3"
    assert settings.maritaca_base_url == "https://custom.api/v1"
    assert settings.tessdata_prefix == "/opt/tessdata"


def test_settings_validations() -> None:
    with pytest.raises(ValueError, match="TJSP_API_MAX_CUSTO_BRL"):
        Settings.carregar(carregar_dotenv=False, env_dict={"TJSP_API_MAX_CUSTO_BRL": "0"})

    with pytest.raises(ValueError, match="TJSP_API_INTERVALO_TJSP"):
        Settings.carregar(carregar_dotenv=False, env_dict={"TJSP_API_INTERVALO_TJSP": "0.5"})

    with pytest.raises(ValueError, match="TJSP_API_MAX_OUTPUT_TOKENS"):
        Settings.carregar(carregar_dotenv=False, env_dict={"TJSP_API_MAX_OUTPUT_TOKENS": "0"})

    with pytest.raises(ValueError, match="tamanho_chunk"):
        Settings.carregar(carregar_dotenv=False, env_dict={"TJSP_TAMANHO_CHUNK": "50"})

    with pytest.raises(ValueError, match="sobreposicao_chunk"):
        Settings.carregar(
            carregar_dotenv=False,
            env_dict={"TJSP_TAMANHO_CHUNK": "500", "TJSP_SOBREPOSICAO_CHUNK": "600"},
        )

    with pytest.raises(ValueError, match="deve ser numérico"):
        Settings.carregar(carregar_dotenv=False, env_dict={"TJSP_API_MAX_CUSTO_BRL": "abc"})

    with pytest.raises(ValueError, match="deve ser inteiro"):
        Settings.carregar(carregar_dotenv=False, env_dict={"TJSP_API_MAX_OUTPUT_TOKENS": "xyz"})

    with pytest.raises(ValueError, match="deve ser booleano"):
        Settings.carregar(carregar_dotenv=False, env_dict={"TJSP_API_HABILITAR_OCR": "talvez"})


def test_get_settings_caching() -> None:
    reset_settings()
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2

    reset_settings()
    s3 = get_settings()
    assert s3 is not s1
    assert s3 == s1


def test_configuracao_api_delegation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TJSP_SQLITE_PATH", "test_sqlite.db")
    monkeypatch.setenv("TJSP_CHROMA_PATH", "test_chroma")
    monkeypatch.setenv("TJSP_API_MAX_CUSTO_BRL", "0.33")

    config = ConfiguracaoAPI.do_ambiente()
    assert config.sqlite_path == Path("test_sqlite.db")
    assert config.chroma_path == Path("test_chroma")
    assert config.max_custo_brl == 0.33
