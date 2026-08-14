from __future__ import annotations

import os

from openai import OpenAI

from .rag import PacoteContextoIA


class ErroMaritaca(RuntimeError):
    """Falha de configuração ou geração na API da Maritaca."""


class ProvedorMaritaca:
    BASE_URL = "https://chat.maritaca.ai/api"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        modelo: str | None = None,
        max_output_tokens: int = 2_000,
        timeout: float = 120.0,
        cliente=None,
    ) -> None:
        chave = api_key or os.environ.get("MARITACA_API_KEY", "")
        if not chave.strip():
            raise ErroMaritaca(
                "MARITACA_API_KEY não configurada. Defina no ambiente ou arquivo .env."
            )
        if max_output_tokens < 1:
            raise ValueError("max_output_tokens deve ser pelo menos 1.")
        self.modelo = modelo or os.environ.get("MARITACA_MODEL", "sabia-4")
        self.max_output_tokens = max_output_tokens
        self.cliente = cliente or OpenAI(
            api_key=chave,
            base_url=self.BASE_URL,
            timeout=timeout,
        )

    def responder(self, pacote: PacoteContextoIA) -> str:
        try:
            resposta = self.cliente.responses.create(
                model=self.modelo,
                instructions=pacote.instrucoes_sistema,
                input=pacote.mensagem_usuario,
                max_output_tokens=self.max_output_tokens,
            )
        except Exception as exc:
            raise ErroMaritaca(f"Falha na API Maritaca: {exc}") from exc

        texto = getattr(resposta, "output_text", None)
        if not texto:
            try:
                texto = resposta.output[0].content[0].text
            except (AttributeError, IndexError, TypeError) as exc:
                raise ErroMaritaca("API Maritaca devolveu resposta sem texto.") from exc
        return str(texto).strip()
