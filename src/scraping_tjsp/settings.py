from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


def _float_ambiente(
    nome: str, padrao: float, env_dict: dict[str, str] | None = None
) -> float:
    origem = env_dict if env_dict is not None else os.environ
    valor = origem.get(nome)
    if valor is None:
        return padrao
    try:
        return float(valor)
    except ValueError as exc:
        raise ValueError(f"{nome} deve ser numérico.") from exc


def _int_ambiente(
    nome: str, padrao: int, env_dict: dict[str, str] | None = None
) -> int:
    origem = env_dict if env_dict is not None else os.environ
    valor = origem.get(nome)
    if valor is None:
        return padrao
    try:
        return int(valor)
    except ValueError as exc:
        raise ValueError(f"{nome} deve ser inteiro.") from exc


def _bool_ambiente(
    nome: str, padrao: bool, env_dict: dict[str, str] | None = None
) -> bool:
    origem = env_dict if env_dict is not None else os.environ
    valor = origem.get(nome)
    if valor is None:
        return padrao
    normalizado = str(valor).strip().casefold()
    if normalizado in {"1", "true", "sim", "yes", "on"}:
        return True
    if normalizado in {"0", "false", "nao", "não", "no", "off"}:
        return False
    raise ValueError(f"{nome} deve ser booleano.")


def _str_ambiente(
    nome: str,
    padrao: str | None = None,
    env_dict: dict[str, str] | None = None,
) -> str | None:
    origem = env_dict if env_dict is not None else os.environ
    valor = origem.get(nome)
    if valor is None or not str(valor).strip():
        return padrao
    return str(valor).strip()


def _path_ambiente(
    nome: str, padrao: Path, env_dict: dict[str, str] | None = None
) -> Path:
    origem = env_dict if env_dict is not None else os.environ
    valor = origem.get(nome)
    if valor is None or not str(valor).strip():
        return padrao
    return Path(str(valor).strip())


@dataclass(slots=True, frozen=True)
class Settings:
    """Configurações globais e centralizadas do scraping_tjsp."""

    # Caminhos
    sqlite_path: Path = Path("data/tjsp.sqlite3")
    chroma_path: Path = Path("data/chroma")
    diretorio_pdfs: Path = Path("data/pdfs")
    saida_path: Path = Path("output/resultados.jsonl")

    # Coleta & Scraping
    intervalo_tjsp: float = 2.0
    max_paginas_tjsp: int = 1
    max_importacao_pdfs: int = 5
    max_mb_pdf: int = 50
    habilitar_ocr: bool = True
    tamanho_chunk: int = 1500
    sobreposicao_chunk: int = 200

    # API & Custos
    max_custo_brl: float = 0.10
    max_output_tokens: int = 2_000
    max_custo_pesquisa_assistida_brl: float = 0.20
    max_custo_analise_documental_brl: float = 0.20

    # Maritaca / LLM
    maritaca_api_key: str | None = None
    maritaca_model: str = "sabia-4"
    maritaca_base_url: str = "https://chat.maritaca.ai/api"
    tessdata_prefix: str | None = None

    def __post_init__(self) -> None:
        if self.max_custo_brl <= 0:
            raise ValueError("TJSP_API_MAX_CUSTO_BRL deve ser positivo.")
        if self.max_output_tokens < 1:
            raise ValueError("TJSP_API_MAX_OUTPUT_TOKENS deve ser pelo menos 1.")
        if self.intervalo_tjsp < 1:
            raise ValueError("TJSP_API_INTERVALO_TJSP deve ser pelo menos 1 segundo.")
        if self.max_paginas_tjsp < 1 or self.max_importacao_pdfs < 1:
            raise ValueError("Limites de coleta TJSP devem ser positivos.")
        if self.max_mb_pdf < 1:
            raise ValueError("TJSP_API_MAX_MB_PDF deve ser positivo.")
        if self.max_custo_pesquisa_assistida_brl <= 0:
            raise ValueError("TJSP_API_MAX_CUSTO_PESQUISA_BRL deve ser positivo.")
        if self.max_custo_analise_documental_brl <= 0:
            raise ValueError("TJSP_API_MAX_CUSTO_ANALISE_BRL deve ser positivo.")
        if self.tamanho_chunk < 100:
            raise ValueError("tamanho_chunk deve ser pelo menos 100.")
        if (
            self.sobreposicao_chunk < 0
            or self.sobreposicao_chunk >= self.tamanho_chunk
        ):
            raise ValueError(
                "sobreposicao_chunk deve ser não-negativo e menor que tamanho_chunk."
            )

    @classmethod
    def carregar(
        cls,
        *,
        env_file: Path | str | None = None,
        env_dict: dict[str, str] | None = None,
        carregar_dotenv: bool = True,
    ) -> Settings:
        """Carrega configurações a partir do ambiente e/ou arquivo .env."""
        if carregar_dotenv and env_dict is None:
            if env_file:
                load_dotenv(dotenv_path=env_file, override=False)
            else:
                load_dotenv(override=False)

        return cls(
            sqlite_path=_path_ambiente(
                "TJSP_SQLITE_PATH", Path("data/tjsp.sqlite3"), env_dict
            ),
            chroma_path=_path_ambiente(
                "TJSP_CHROMA_PATH", Path("data/chroma"), env_dict
            ),
            diretorio_pdfs=_path_ambiente(
                "TJSP_DIRETORIO_PDFS", Path("data/pdfs"), env_dict
            ),
            saida_path=_path_ambiente(
                "TJSP_SAIDA_PATH", Path("output/resultados.jsonl"), env_dict
            ),
            intervalo_tjsp=_float_ambiente(
                "TJSP_API_INTERVALO_TJSP", 2.0, env_dict
            ),
            max_paginas_tjsp=_int_ambiente(
                "TJSP_API_MAX_PAGINAS_TJSP", 1, env_dict
            ),
            max_importacao_pdfs=_int_ambiente(
                "TJSP_API_MAX_IMPORTACAO_PDFS", 5, env_dict
            ),
            max_mb_pdf=_int_ambiente("TJSP_API_MAX_MB_PDF", 50, env_dict),
            habilitar_ocr=_bool_ambiente(
                "TJSP_API_HABILITAR_OCR", True, env_dict
            ),
            tamanho_chunk=_int_ambiente("TJSP_TAMANHO_CHUNK", 1500, env_dict),
            sobreposicao_chunk=_int_ambiente(
                "TJSP_SOBREPOSICAO_CHUNK", 200, env_dict
            ),
            max_custo_brl=_float_ambiente(
                "TJSP_API_MAX_CUSTO_BRL", 0.10, env_dict
            ),
            max_output_tokens=_int_ambiente(
                "TJSP_API_MAX_OUTPUT_TOKENS", 2_000, env_dict
            ),
            max_custo_pesquisa_assistida_brl=_float_ambiente(
                "TJSP_API_MAX_CUSTO_PESQUISA_BRL", 0.20, env_dict
            ),
            max_custo_analise_documental_brl=_float_ambiente(
                "TJSP_API_MAX_CUSTO_ANALISE_BRL", 0.20, env_dict
            ),
            maritaca_api_key=_str_ambiente("MARITACA_API_KEY", None, env_dict),
            maritaca_model=_str_ambiente("MARITACA_MODEL", "sabia-4", env_dict)
            or "sabia-4",
            maritaca_base_url=_str_ambiente(
                "MARITACA_BASE_URL", "https://chat.maritaca.ai/api", env_dict
            )
            or "https://chat.maritaca.ai/api",
            tessdata_prefix=_str_ambiente("TESSDATA_PREFIX", None, env_dict),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna instância singleton com cache das configurações do sistema."""
    return Settings.carregar()


def reset_settings() -> None:
    """Limpa o cache das configurações (útil para testes unitários)."""
    get_settings.cache_clear()
