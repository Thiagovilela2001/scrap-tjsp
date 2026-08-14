import hashlib
from pathlib import Path

import pymupdf

from scraping_tjsp.models import DocumentoBaixado
from scraping_tjsp.processor import ProcessadorPDF


def _documento(tmp_path: Path, texto: str) -> DocumentoBaixado:
    caminho = tmp_path / "123.pdf"
    pdf = pymupdf.open()
    pagina = pdf.new_page(width=600, height=5000)
    if texto:
        pagina.insert_textbox((40, 40, 560, 4960), texto, fontsize=11)
    pdf.save(caminho)
    pdf.close()
    sha256 = hashlib.sha256(caminho.read_bytes()).hexdigest()
    return DocumentoBaixado(
        cd_acordao="123",
        url_origem="https://esaj.tjsp.jus.br/cjsg/getArquivo.do?cdAcordao=123",
        caminho_local=str(caminho),
        mime_type="application/pdf",
        tamanho_bytes=caminho.stat().st_size,
        sha256=sha256,
    )


def test_extrai_por_pagina_e_cria_chunks_estaveis(tmp_path: Path):
    texto = " ".join(f"palavra{i}" for i in range(250))
    documento = _documento(tmp_path, texto)
    processador = ProcessadorPDF(
        tamanho_chunk=300,
        sobreposicao=50,
        minimo_caracteres_ocr=10,
        habilitar_ocr=False,
    )

    resultado = processador.processar(documento)

    assert resultado.status == "processado"
    assert resultado.total_paginas == 1
    assert resultado.paginas[0].metodo == "nativo"
    assert len(resultado.chunks) > 1
    assert resultado.chunks[0].identificador == "acordao:123:pagina:1:chunk:1"
    assert all(chunk.pagina == 1 for chunk in resultado.chunks)


def test_usa_ocr_quando_texto_nativo_e_insuficiente(tmp_path: Path, monkeypatch):
    documento = _documento(tmp_path, "")
    processador = ProcessadorPDF(minimo_caracteres_ocr=10)
    monkeypatch.setattr(
        processador,
        "_extrair_ocr",
        lambda pagina: "Texto recuperado por reconhecimento \u00f3ptico.",
    )

    resultado = processador.processar(documento)

    assert resultado.status == "processado"
    assert resultado.paginas_ocr == 1
    assert resultado.paginas[0].metodo == "ocr"
    assert resultado.chunks[0].pagina == 1


def test_marca_parcial_quando_ocr_falha(tmp_path: Path, monkeypatch):
    documento = _documento(tmp_path, "")
    processador = ProcessadorPDF(minimo_caracteres_ocr=10)

    def falhar_ocr(pagina):
        raise RuntimeError("Tesseract ausente")

    monkeypatch.setattr(processador, "_extrair_ocr", falhar_ocr)

    resultado = processador.processar(documento)

    assert resultado.status == "parcial"
    assert resultado.paginas[0].metodo == "vazio"
    assert "Tesseract ausente" in resultado.paginas[0].erro
    assert resultado.chunks == ()
