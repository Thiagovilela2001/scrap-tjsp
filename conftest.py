"""Falha cedo quando pytest usa dependências incompatíveis do Python global."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

import pytest

VERSOES_MINIMAS = {
    "fastapi": (0, 139),
    "httpx": (0, 28),
    "starlette": (0, 46),
}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Executa testes marcados que acessam o portal público real do TJSP.",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--run-integration"):
        return
    ignorar = pytest.mark.skip(reason="requer --run-integration e acesso ao TJSP")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(ignorar)


def pytest_sessionstart(session: pytest.Session) -> None:
    incompatibilidades = []
    for pacote, minima in VERSOES_MINIMAS.items():
        try:
            instalada = version(pacote)
        except PackageNotFoundError:
            incompatibilidades.append(f"{pacote} ausente")
            continue
        if _partes_numericas(instalada) < minima:
            esperada = ".".join(str(item) for item in minima)
            incompatibilidades.append(f"{pacote} {instalada} (exige >= {esperada})")

    if incompatibilidades:
        detalhes = ", ".join(incompatibilidades)
        pytest.exit(
            "Ambiente de testes incompatível: "
            f"{detalhes}.\n"
            "No Windows, execute: .\\.venv\\Scripts\\python.exe -m pytest\n"
            "Para criar ou sincronizar o ambiente: "
            "powershell -ExecutionPolicy Bypass -File scripts/bootstrap-dev.ps1",
            returncode=4,
        )


def _partes_numericas(valor: str) -> tuple[int, ...]:
    partes = []
    for parte in valor.split("."):
        digitos = "".join(caractere for caractere in parte if caractere.isdigit())
        if not digitos:
            break
        partes.append(int(digitos))
    return tuple(partes)
