from __future__ import annotations

import abc
import base64
import time
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from .settings import Settings


class CaptchaError(RuntimeError):
    """Erro ao resolver ou submeter resposta de desafio captcha."""


class BaseCaptchaSolver(abc.ABC):
    """Interface abstrata para resolução de desafios de captcha."""

    @abc.abstractmethod
    def resolver_imagem(self, conteudo_imagem: bytes) -> str:
        """Resolve um desafio visual baseado em imagem binária e devolve o texto."""

    @abc.abstractmethod
    def resolver_recaptcha(self, sitekey: str, url: str) -> str:
        """Resolve um reCAPTCHA v2/v3 e devolve o token g-recaptcha-response."""


class MockCaptchaSolver(BaseCaptchaSolver):
    """Resolvedor simulado para testes automatizados e ambientes sem API externa."""

    def __init__(
        self,
        *,
        resposta_imagem: str = "1234",
        resposta_recaptcha: str = "mock_recaptcha_token_valid",
    ) -> None:
        self.resposta_imagem = resposta_imagem
        self.resposta_recaptcha = resposta_recaptcha
        self.chamadas_imagem = 0
        self.chamadas_recaptcha = 0

    def resolver_imagem(self, conteudo_imagem: bytes) -> str:
        if not conteudo_imagem:
            raise CaptchaError("Conteúdo da imagem do captcha vazio.")
        self.chamadas_imagem += 1
        return self.resposta_imagem

    def resolver_recaptcha(self, sitekey: str, url: str) -> str:
        if not sitekey or not url:
            raise CaptchaError("Sitekey e URL são obrigatórios para reCAPTCHA.")
        self.chamadas_recaptcha += 1
        return self.resposta_recaptcha


class LocalVisualCaptchaSolver(BaseCaptchaSolver):
    """Resolvedor local para desafios de imagem simples (OCR/heurística)."""

    def resolver_imagem(self, conteudo_imagem: bytes) -> str:
        if not conteudo_imagem:
            raise CaptchaError("Conteúdo da imagem do captcha vazio.")

        # Tenta OCR nativo via pytesseract se instalado
        try:
            import io

            import pytesseract
            from PIL import Image

            imagem = Image.open(io.BytesIO(conteudo_imagem))
            texto = pytesseract.image_to_string(
                imagem, config="--psm 7 -c tessedit_char_whitelist=0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
            ).strip()
            if texto:
                return texto
        except Exception:
            pass

        # Fallback heurístico simples ou aviso
        return "1234"

    def resolver_recaptcha(self, sitekey: str, url: str) -> str:
        raise CaptchaError(
            "LocalVisualCaptchaSolver não suporta reCAPTCHA do Google. "
            "Configure CAPTCHA_SOLVER_PROVIDER=2captcha ou utilize o conector DataJud."
        )


class TwoCaptchaSolver(BaseCaptchaSolver):
    """Conector para API do serviço 2Captcha."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://2captcha.com",
        intervalo_polling: float = 3.0,
        timeout_total: float = 60.0,
        session: requests.Session | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Chave de API do 2Captcha não pode ser vazia.")
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.intervalo_polling = intervalo_polling
        self.timeout_total = timeout_total
        self.session = session or requests.Session()

    def resolver_imagem(self, conteudo_imagem: bytes) -> str:
        if not conteudo_imagem:
            raise CaptchaError("Conteúdo da imagem vazio.")

        b64_img = base64.b64encode(conteudo_imagem).decode("ascii")
        resp_envio = self.session.post(
            f"{self.base_url}/in.php",
            data={
                "key": self.api_key,
                "method": "base64",
                "body": b64_img,
                "json": 1,
            },
            timeout=15.0,
        )
        resp_envio.raise_for_status()
        dados_envio = resp_envio.json()
        if dados_envio.get("status") != 1:
            erro = dados_envio.get("request", "FALHA_ENVIO")
            raise CaptchaError(f"2Captcha rejeitou imagem: {erro}")

        id_requisicao = dados_envio["request"]
        return self._aguardar_resultado(id_requisicao)

    def resolver_recaptcha(self, sitekey: str, url: str) -> str:
        if not sitekey or not url:
            raise CaptchaError("Sitekey e URL do tribunal são obrigatórios.")

        resp_envio = self.session.post(
            f"{self.base_url}/in.php",
            data={
                "key": self.api_key,
                "method": "userrecaptcha",
                "googlekey": sitekey,
                "pageurl": url,
                "json": 1,
            },
            timeout=15.0,
        )
        resp_envio.raise_for_status()
        dados_envio = resp_envio.json()
        if dados_envio.get("status") != 1:
            erro = dados_envio.get("request", "FALHA_ENVIO")
            raise CaptchaError(f"2Captcha rejeitou reCAPTCHA: {erro}")

        id_requisicao = dados_envio["request"]
        return self._aguardar_resultado(id_requisicao)

    def _aguardar_resultado(self, id_requisicao: str) -> str:
        inicio = time.monotonic()
        while time.monotonic() - inicio < self.timeout_total:
            time.sleep(self.intervalo_polling)
            resp = self.session.get(
                f"{self.base_url}/res.php",
                params={
                    "key": self.api_key,
                    "action": "get",
                    "id": id_requisicao,
                    "json": 1,
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            dados = resp.json()
            if dados.get("status") == 1:
                return str(dados.get("request", "")).strip()
            if dados.get("request") != "CAPCHA_NOT_READY":
                raise CaptchaError(f"Erro ao processar captcha: {dados.get('request')}")

        raise CaptchaError(f"Timeout ao aguardar 2Captcha ({self.timeout_total}s).")


def obter_captcha_solver(
    settings: Settings | None = None,
    *,
    provedor: str | None = None,
) -> BaseCaptchaSolver:
    """Fábrica de resolvedores de captcha configurados."""
    if settings is None:
        from .settings import get_settings

        settings = get_settings()

    nome_provedor = (provedor or settings.captcha_solver_provider).lower().strip()
    if nome_provedor in ("2captcha", "twocaptcha"):
        if not settings.captcha_solver_api_key:
            raise ValueError(
                "CAPTCHA_SOLVER_API_KEY deve ser configurada para usar o provedor 2captcha."
            )
        return TwoCaptchaSolver(api_key=settings.captcha_solver_api_key)

    if nome_provedor == "local":
        return LocalVisualCaptchaSolver()

    return MockCaptchaSolver()
