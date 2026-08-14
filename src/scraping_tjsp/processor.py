from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from pathlib import Path

import pymupdf

from .models import (
    ChunkJuridico,
    DocumentoBaixado,
    PaginaExtraida,
    ResultadoProcessamento,
)


class ProcessamentoPDFError(RuntimeError):
    """Falha ao abrir, validar ou extrair um inteiro teor."""


class ProcessadorPDF:
    def __init__(
        self,
        *,
        tamanho_chunk: int = 1500,
        sobreposicao: int = 200,
        minimo_caracteres_ocr: int = 80,
        habilitar_ocr: bool = True,
        idioma_ocr: str = "por",
        dpi_ocr: int = 300,
        tessdata: Path | str | None = None,
    ) -> None:
        if tamanho_chunk < 200:
            raise ValueError("Chunk deve ter pelo menos 200 caracteres.")
        if sobreposicao < 0 or sobreposicao >= tamanho_chunk:
            raise ValueError(
                "Sobreposi\u00e7\u00e3o deve ficar entre 0 e tamanho do chunk - 1."
            )
        if minimo_caracteres_ocr < 0:
            raise ValueError(
                "M\u00ednimo de caracteres para OCR n\u00e3o pode ser negativo."
            )
        self.tamanho_chunk = tamanho_chunk
        self.sobreposicao = sobreposicao
        self.minimo_caracteres_ocr = minimo_caracteres_ocr
        self.habilitar_ocr = habilitar_ocr
        self.idioma_ocr = idioma_ocr
        self.dpi_ocr = dpi_ocr
        self.tessdata = _descobrir_tessdata(idioma_ocr, tessdata)

    def processar(self, documento: DocumentoBaixado) -> ResultadoProcessamento:
        caminho = Path(documento.caminho_local)
        self._validar_arquivo(caminho, documento.sha256)

        try:
            pdf = pymupdf.open(caminho)
        except Exception as exc:
            raise ProcessamentoPDFError(
                f"PDF n\u00e3o p\u00f4de ser aberto: {exc}"
            ) from exc

        try:
            if pdf.needs_pass:
                raise ProcessamentoPDFError("PDF protegido por senha.")
            if pdf.page_count < 1:
                raise ProcessamentoPDFError("PDF sem p\u00e1ginas.")

            paginas = tuple(
                self._extrair_pagina(pagina, numero)
                for numero, pagina in enumerate(pdf, start=1)
            )
        except ProcessamentoPDFError:
            raise
        except Exception as exc:
            raise ProcessamentoPDFError(
                f"Falha durante extra\u00e7\u00e3o: {exc}"
            ) from exc
        finally:
            pdf.close()

        chunks = tuple(
            chunk
            for pagina in paginas
            for chunk in self._criar_chunks(documento.cd_acordao, pagina)
        )
        parcial = any(not pagina.texto or pagina.erro for pagina in paginas)
        return ResultadoProcessamento(
            cd_acordao=documento.cd_acordao,
            caminho_local=str(caminho),
            sha256=documento.sha256,
            total_paginas=len(paginas),
            paginas=paginas,
            chunks=chunks,
            status="parcial" if parcial else "processado",
        )

    def _extrair_pagina(self, pagina, numero: int) -> PaginaExtraida:
        texto_nativo = _limpar_texto(pagina.get_text("text", sort=True))
        if _quantidade_util(texto_nativo) >= self.minimo_caracteres_ocr:
            return PaginaExtraida(numero, texto_nativo, "nativo")

        if not self.habilitar_ocr:
            metodo = "nativo" if texto_nativo else "vazio"
            return PaginaExtraida(numero, texto_nativo, metodo)

        try:
            texto_ocr = _limpar_texto(self._extrair_ocr(pagina))
        except Exception as exc:
            metodo = "nativo" if texto_nativo else "vazio"
            return PaginaExtraida(
                numero,
                texto_nativo,
                metodo,
                f"OCR indispon\u00edvel ou falhou: {exc}"[:1000],
            )

        if _quantidade_util(texto_ocr) > _quantidade_util(texto_nativo):
            return PaginaExtraida(numero, texto_ocr, "ocr")
        metodo = "nativo" if texto_nativo else "vazio"
        return PaginaExtraida(numero, texto_nativo, metodo)

    def _extrair_ocr(self, pagina) -> str:
        if self.tessdata is None:
            raise RuntimeError(
                f"dados Tesseract para idioma {self.idioma_ocr!r} não encontrados"
            )
        textpage = pagina.get_textpage_ocr(
            language=self.idioma_ocr,
            dpi=self.dpi_ocr,
            full=True,
            tessdata=str(self.tessdata),
        )
        return pagina.get_text("text", textpage=textpage, sort=True)

    def _criar_chunks(
        self, cd_acordao: str, pagina: PaginaExtraida
    ) -> tuple[ChunkJuridico, ...]:
        partes = _fatiar_texto(
            pagina.texto,
            tamanho=self.tamanho_chunk,
            sobreposicao=self.sobreposicao,
        )
        return tuple(
            ChunkJuridico(cd_acordao, pagina.numero, indice, texto)
            for indice, texto in enumerate(partes, start=1)
        )

    @staticmethod
    def _validar_arquivo(caminho: Path, sha256_esperado: str) -> None:
        if not caminho.is_file():
            raise ProcessamentoPDFError(f"PDF n\u00e3o encontrado: {caminho}")
        with caminho.open("rb") as arquivo:
            if arquivo.read(5) != b"%PDF-":
                raise ProcessamentoPDFError("Arquivo n\u00e3o possui assinatura PDF.")
            arquivo.seek(0)
            sha256_atual = hashlib.file_digest(arquivo, "sha256").hexdigest()
        if sha256_atual != sha256_esperado:
            raise ProcessamentoPDFError(
                "SHA-256 do PDF diverge do download registrado."
            )


def _limpar_texto(texto: str) -> str:
    texto = unicodedata.normalize("NFC", texto).replace("\u00a0", " ")
    texto = re.sub(r"(?<=\w)-\n(?=\w)", "", texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r" *\n *", "\n", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _quantidade_util(texto: str) -> int:
    return sum(not caractere.isspace() for caractere in texto)


def _descobrir_tessdata(
    idiomas: str, caminho_configurado: Path | str | None
) -> Path | None:
    candidatos: list[Path] = []
    if caminho_configurado:
        candidatos.append(Path(caminho_configurado))
    if caminho_ambiente := os.environ.get("TESSDATA_PREFIX"):
        candidatos.append(Path(caminho_ambiente))
    candidatos.extend(
        (
            Path("data/tessdata"),
            Path(r"C:\Program Files\Tesseract-OCR\tessdata"),
        )
    )
    nomes = [idioma for idioma in idiomas.split("+") if idioma]
    for candidato in candidatos:
        if all((candidato / f"{idioma}.traineddata").is_file() for idioma in nomes):
            return candidato.resolve()
    return None


def _fatiar_texto(texto: str, *, tamanho: int, sobreposicao: int) -> list[str]:
    texto = texto.strip()
    if not texto:
        return []
    if len(texto) <= tamanho:
        return [texto]

    partes: list[str] = []
    inicio = 0
    while inicio < len(texto):
        fim = min(inicio + tamanho, len(texto))
        if fim < len(texto):
            corte = max(
                texto.rfind("\n", inicio + tamanho // 2, fim),
                texto.rfind(". ", inicio + tamanho // 2, fim),
                texto.rfind(" ", inicio + tamanho // 2, fim),
            )
            if corte > inicio:
                fim = corte + 1
        parte = texto[inicio:fim].strip()
        if parte:
            partes.append(parte)
        if fim >= len(texto):
            break
        proximo = max(0, fim - sobreposicao)
        espaco = texto.find(" ", proximo, fim)
        inicio = espaco + 1 if espaco >= 0 else proximo
    return partes
