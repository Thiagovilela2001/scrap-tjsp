from __future__ import annotations

import hashlib
import os
from contextlib import suppress
from pathlib import Path

from .client import TJSPClient
from .models import Decisao, DocumentoBaixado


class DownloadPDFError(RuntimeError):
    """Falha controlada ao obter ou validar inteiro teor."""


class PDFDownloader:
    def __init__(
        self,
        cliente: TJSPClient,
        *,
        diretorio: Path | str = Path("data/pdfs"),
        limite_bytes: int = 50 * 1024 * 1024,
    ) -> None:
        if limite_bytes < 1024:
            raise ValueError("Limite de PDF deve ser pelo menos 1024 bytes.")
        self.cliente = cliente
        self.diretorio = Path(diretorio)
        self.limite_bytes = limite_bytes

    def baixar(self, decisao: Decisao) -> DocumentoBaixado:
        if not decisao.cd_acordao.isdigit():
            raise DownloadPDFError("Identificador de acórdão inválido.")

        self.diretorio.mkdir(parents=True, exist_ok=True)
        destino = self.diretorio / f"{decisao.cd_acordao}.pdf"
        existente = self._arquivo_existente(decisao, destino)
        if existente is not None:
            return existente

        temporario = destino.with_suffix(".pdf.part")
        with suppress(FileNotFoundError):
            temporario.unlink()

        try:
            resposta = self.cliente.obter_pdf(decisao.inteiro_teor_url)
            with resposta:
                tamanho_declarado = _inteiro_positivo(
                    resposta.headers.get("Content-Length")
                )
                if tamanho_declarado and tamanho_declarado > self.limite_bytes:
                    raise DownloadPDFError(
                        f"PDF excede limite de {self.limite_bytes} bytes."
                    )

                hash_arquivo = hashlib.sha256()
                tamanho = 0
                primeiro_bloco = True
                with temporario.open("wb") as arquivo:
                    for bloco in resposta.iter_content(chunk_size=64 * 1024):
                        if not bloco:
                            continue
                        if primeiro_bloco:
                            primeiro_bloco = False
                            if not bloco.startswith(b"%PDF-"):
                                tipo = resposta.headers.get(
                                    "Content-Type", "desconhecido"
                                )
                                raise DownloadPDFError(
                                    f"TJSP não devolveu PDF válido; Content-Type={tipo}."
                                )
                        tamanho += len(bloco)
                        if tamanho > self.limite_bytes:
                            raise DownloadPDFError(
                                f"PDF excede limite de {self.limite_bytes} bytes durante download."
                            )
                        arquivo.write(bloco)
                        hash_arquivo.update(bloco)

                if primeiro_bloco:
                    raise DownloadPDFError("TJSP devolveu arquivo vazio.")

            os.replace(temporario, destino)
            return DocumentoBaixado(
                cd_acordao=decisao.cd_acordao,
                url_origem=decisao.inteiro_teor_url,
                caminho_local=str(destino),
                mime_type="application/pdf",
                tamanho_bytes=tamanho,
                sha256=hash_arquivo.hexdigest(),
            )
        except DownloadPDFError:
            with suppress(FileNotFoundError):
                temporario.unlink()
            raise
        except Exception as exc:
            with suppress(FileNotFoundError):
                temporario.unlink()
            raise DownloadPDFError(f"Falha ao baixar PDF: {exc}") from exc

    def _arquivo_existente(
        self, decisao: Decisao, destino: Path
    ) -> DocumentoBaixado | None:
        if not destino.is_file():
            return None
        tamanho = destino.stat().st_size
        if tamanho > self.limite_bytes:
            raise DownloadPDFError("PDF existente excede limite configurado.")
        with destino.open("rb") as arquivo:
            if arquivo.read(5) != b"%PDF-":
                return None
            arquivo.seek(0)
            hash_arquivo = hashlib.file_digest(arquivo, "sha256").hexdigest()
        return DocumentoBaixado(
            cd_acordao=decisao.cd_acordao,
            url_origem=decisao.inteiro_teor_url,
            caminho_local=str(destino),
            mime_type="application/pdf",
            tamanho_bytes=tamanho,
            sha256=hash_arquivo,
            reutilizado=True,
        )


def _inteiro_positivo(valor: str | None) -> int | None:
    try:
        numero = int(valor) if valor is not None else 0
    except (TypeError, ValueError):
        return None
    return numero if numero > 0 else None
