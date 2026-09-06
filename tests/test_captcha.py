import pytest
import requests

from scraping_tjsp.captcha import (
    CaptchaError,
    LocalVisualCaptchaSolver,
    MockCaptchaSolver,
    TwoCaptchaSolver,
    obter_captcha_solver,
)
from scraping_tjsp.client import TJSPClient
from scraping_tjsp.settings import Settings


def _resposta_http(status: int, conteudo: bytes, headers: dict | None = None) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r._content = conteudo
    r._content_consumed = True
    if headers:
        r.headers.update(headers)
    return r


def test_mock_captcha_solver():
    solver = MockCaptchaSolver(resposta_imagem="9999", resposta_recaptcha="token_abc")
    assert solver.resolver_imagem(b"dummy_bytes") == "9999"
    assert solver.chamadas_imagem == 1

    assert solver.resolver_recaptcha("sitekey123", "https://esaj.tjam.jus.br") == "token_abc"
    assert solver.chamadas_recaptcha == 1

    with pytest.raises(CaptchaError, match="vazio"):
        solver.resolver_imagem(b"")

    with pytest.raises(CaptchaError, match="obrigatórios"):
        solver.resolver_recaptcha("", "https://exemplo.com")


def test_local_visual_captcha_solver():
    solver = LocalVisualCaptchaSolver()
    # Imagem simulada
    texto = solver.resolver_imagem(b"fake_image_bytes")
    assert texto

    with pytest.raises(CaptchaError, match="não suporta reCAPTCHA"):
        solver.resolver_recaptcha("key", "https://esaj.tjce.jus.br")


def test_two_captcha_solver_fluxo_imagem():
    chamadas = []

    class FakeSession:
        def post(self, url, data=None, **kwargs):
            chamadas.append(("POST", url, data))
            return _resposta_http(200, b'{"status": 1, "request": "REQ_123"}')

        def get(self, url, params=None, **kwargs):
            chamadas.append(("GET", url, params))
            return _resposta_http(200, b'{"status": 1, "request": "RESULTADO_OCR"}')

    solver = TwoCaptchaSolver(
        api_key="minha_chave",
        session=FakeSession(),
        intervalo_polling=0.01,
    )
    resultado = solver.resolver_imagem(b"bytes_da_imagem")
    assert resultado == "RESULTADO_OCR"
    assert len(chamadas) == 2
    assert chamadas[0][0] == "POST"
    assert chamadas[0][2]["method"] == "base64"
    assert chamadas[1][0] == "GET"
    assert chamadas[1][2]["id"] == "REQ_123"


def test_two_captcha_solver_fluxo_recaptcha():
    class FakeSession:
        def post(self, url, data=None, **kwargs):
            return _resposta_http(200, b'{"status": 1, "request": "REQ_RECAPTCHA"}')

        def get(self, url, params=None, **kwargs):
            return _resposta_http(200, b'{"status": 1, "request": "TOKEN_VALIDO_RECAPTCHA"}')

    solver = TwoCaptchaSolver(
        api_key="minha_chave",
        session=FakeSession(),
        intervalo_polling=0.01,
    )
    token = solver.resolver_recaptcha("sitekey_tjce", "https://esaj.tjce.jus.br")
    assert token == "TOKEN_VALIDO_RECAPTCHA"


def test_two_captcha_trata_rejeicao():
    class FakeSession:
        def post(self, url, data=None, **kwargs):
            return _resposta_http(200, b'{"status": 0, "request": "ERROR_ZERO_BALANCE"}')

    solver = TwoCaptchaSolver(
        api_key="minha_chave",
        session=FakeSession(),
    )
    with pytest.raises(CaptchaError, match="ERROR_ZERO_BALANCE"):
        solver.resolver_imagem(b"teste")


def test_obter_captcha_solver_factory():
    st_mock = Settings.carregar(carregar_dotenv=False, env_dict={"CAPTCHA_SOLVER_PROVIDER": "mock"})
    assert isinstance(obter_captcha_solver(st_mock), MockCaptchaSolver)

    st_local = Settings.carregar(carregar_dotenv=False, env_dict={"CAPTCHA_SOLVER_PROVIDER": "local"})
    assert isinstance(obter_captcha_solver(st_local), LocalVisualCaptchaSolver)

    st_2captcha_sem_key = Settings.carregar(
        carregar_dotenv=False,
        env_dict={"CAPTCHA_SOLVER_PROVIDER": "2captcha"},
    )
    with pytest.raises(ValueError, match="CAPTCHA_SOLVER_API_KEY"):
        obter_captcha_solver(st_2captcha_sem_key)

    st_2captcha_com_key = Settings.carregar(
        carregar_dotenv=False,
        env_dict={
            "CAPTCHA_SOLVER_PROVIDER": "2captcha",
            "CAPTCHA_SOLVER_API_KEY": "chave_123",
        },
    )
    solver_2cap = obter_captcha_solver(st_2captcha_com_key)
    assert isinstance(solver_2cap, TwoCaptchaSolver)
    assert solver_2cap.api_key == "chave_123"


def test_obter_pdf_resolve_desafio_recaptcha_com_solver():
    html_captcha = b"""
    <html><body>
      <form action="/cjsg/getArquivo.do" method="POST">
        <input type="hidden" name="cdAcordao" value="987654" />
        <input type="hidden" name="cdForo" value="0" />
        <input type="hidden" name="uuidCaptcha" value="" />
        <div class="g-recaptcha" data-sitekey="sitekey_tjam_123"></div>
      </form>
    </body></html>
    """

    conteudo_pdf = b"%PDF-1.4\nacordao liberado apos captcha"

    chamadas = []

    def fake_request(metodo, url, **kwargs):
        chamadas.append((metodo, url, kwargs))
        if metodo == "GET":
            return _resposta_http(200, html_captcha, {"Content-Type": "text/html;charset=UTF-8"})
        if metodo == "POST":
            return _resposta_http(200, conteudo_pdf, {"Content-Type": "application/pdf"})
        raise ValueError("Metodo inesperado")

    solver_mock = MockCaptchaSolver(resposta_recaptcha="token_aprovado")
    cliente = TJSPClient(tribunal="tjam", intervalo=1.0, captcha_solver=solver_mock)
    cliente.session.request = fake_request

    resposta = cliente.obter_pdf(
        "https://consultasaj.tjam.jus.br/cjsg/getArquivo.do?cdAcordao=987654&cdForo=0"
    )

    assert resposta.headers["Content-Type"] == "application/pdf"
    assert resposta.content.startswith(b"%PDF-")
    assert solver_mock.chamadas_recaptcha == 1
    assert len(chamadas) == 2
    assert chamadas[1][0] == "POST"
    assert chamadas[1][2]["data"]["g-recaptcha-response"] == "token_aprovado"
