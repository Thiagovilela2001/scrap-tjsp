from __future__ import annotations

import os
import time

from openai import OpenAI

from .rag import PacoteContextoIA, RespostaIA


class ErroMaritaca(RuntimeError):
    """Falha de configuração ou geração na API da Maritaca."""

    def __init__(self, mensagem: str, *, duracao_ms: int | None = None) -> None:
        super().__init__(mensagem)
        self.duracao_ms = duracao_ms


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

    def responder(self, pacote: PacoteContextoIA) -> RespostaIA:
        inicio = time.perf_counter()
        try:
            resposta = self.cliente.responses.create(
                model=self.modelo,
                instructions=pacote.instrucoes_sistema,
                input=pacote.mensagem_usuario,
                max_output_tokens=self.max_output_tokens,
            )
        except Exception as exc:
            duracao_ms = round((time.perf_counter() - inicio) * 1000)
            raise ErroMaritaca(
                f"Falha na API Maritaca: {exc}", duracao_ms=duracao_ms
            ) from exc

        texto = getattr(resposta, "output_text", None)
        if not texto:
            try:
                texto = resposta.output[0].content[0].text
            except (AttributeError, IndexError, TypeError) as exc:
                duracao_ms = round((time.perf_counter() - inicio) * 1000)
                raise ErroMaritaca(
                    "API Maritaca devolveu resposta sem texto.",
                    duracao_ms=duracao_ms,
                ) from exc
        uso = getattr(resposta, "usage", None)
        return RespostaIA(
            texto=str(texto).strip(),
            provedor="maritaca",
            modelo=str(getattr(resposta, "model", None) or self.modelo),
            resposta_id=str(getattr(resposta, "id", "") or ""),
            tokens_entrada=_inteiro_opcional(uso, "input_tokens"),
            tokens_saida=_inteiro_opcional(uso, "output_tokens"),
            tokens_total=_inteiro_opcional(uso, "total_tokens"),
            duracao_ms=round((time.perf_counter() - inicio) * 1000),
        )


def _inteiro_opcional(objeto, atributo: str) -> int | None:
    valor = getattr(objeto, atributo, None)
    return int(valor) if valor is not None else None
