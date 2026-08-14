from pathlib import Path

import pytest

from scraping_tjsp.downloader import DownloadPDFError, PDFDownloader
from scraping_tjsp.models import Decisao


class RespostaFalsa:
    def __init__(self, conteudo: bytes, *, content_type: str = "application/pdf"):
        self.conteudo = conteudo
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(conteudo)),
        }

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def iter_content(self, chunk_size: int):
        yield self.conteudo


class ClienteFalso:
    def __init__(self, resposta: RespostaFalsa):
        self.resposta = resposta
        self.chamadas = 0

    def obter_pdf(self, url: str):
        self.chamadas += 1
        return self.resposta


def decisao() -> Decisao:
    return Decisao(
        processo="1000123-45.2023.8.26.0100",
        cd_acordao="123",
        cd_foro="0",
        classe="Apelação Cível",
        assunto="Contratos",
        relator="Maria Silva",
        comarca="São Paulo",
        orgao_julgador="1ª Câmara",
        data_julgamento="01/08/2026",
        data_publicacao="02/08/2026",
        ementa="Texto.",
        inteiro_teor_url=(
            "https://esaj.tjsp.jus.br/cjsg/getArquivo.do"
            "?casChecked=true&cdAcordao=123&cdForo=0"
        ),
    )


def test_baixa_pdf_atomico_com_hash(tmp_path: Path):
    conteudo = b"%PDF-1.4\nconteudo de teste"
    cliente = ClienteFalso(RespostaFalsa(conteudo))
    documento = PDFDownloader(cliente, diretorio=tmp_path, limite_bytes=1024).baixar(
        decisao()
    )

    assert Path(documento.caminho_local).read_bytes() == conteudo
    assert documento.tamanho_bytes == len(conteudo)
    assert len(documento.sha256) == 64
    assert not documento.reutilizado
    assert not (tmp_path / "123.pdf.part").exists()


def test_reutiliza_pdf_valido_sem_requisicao(tmp_path: Path):
    (tmp_path / "123.pdf").write_bytes(b"%PDF-1.4\nja existe")
    cliente = ClienteFalso(RespostaFalsa(b"nao deve ser usado"))

    documento = PDFDownloader(cliente, diretorio=tmp_path, limite_bytes=1024).baixar(
        decisao()
    )

    assert documento.reutilizado
    assert cliente.chamadas == 0


def test_recusa_html_e_remove_temporario(tmp_path: Path):
    cliente = ClienteFalso(
        RespostaFalsa(b"<html>login</html>", content_type="text/html")
    )

    with pytest.raises(DownloadPDFError, match="não devolveu PDF"):
        PDFDownloader(cliente, diretorio=tmp_path, limite_bytes=1024).baixar(decisao())

    assert not (tmp_path / "123.pdf").exists()
    assert not (tmp_path / "123.pdf.part").exists()


def test_recusa_tamanho_declarado_acima_do_limite(tmp_path: Path):
    resposta = RespostaFalsa(b"%PDF-1.4\n" + b"x" * 2000)
    cliente = ClienteFalso(resposta)

    with pytest.raises(DownloadPDFError, match="excede limite"):
        PDFDownloader(cliente, diretorio=tmp_path, limite_bytes=1024).baixar(decisao())
