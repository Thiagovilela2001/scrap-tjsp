from __future__ import annotations

import random
import threading
import time


class TokenBucket:
    """Limitador de taxa thread-safe baseado em Token Bucket com jitter.

    Garante espaçamento suave entre requisições respeitando o intervalo mínimo,
    com jitter aleatório para evitar padrões previsíveis de tráfego.
    """

    def __init__(
        self,
        intervalo: float = 2.0,
        *,
        capacidade: float = 1.0,
        jitter_max: float = 0.20,
    ) -> None:
        if intervalo < 1.0:
            raise ValueError("Intervalo mínimo permitido é 1 segundo.")
        self.intervalo = float(intervalo)
        self.taxa = 1.0 / self.intervalo
        self.capacidade = float(capacidade)
        self.tokens = float(capacidade)
        self.jitter_max = max(0.0, float(jitter_max))
        self.ultimo = time.monotonic()
        self._lock = threading.Lock()

    def aguardar(self, tokens: float = 1.0) -> None:
        with self._lock:
            agora = time.monotonic()
            decorrido = agora - self.ultimo
            self.ultimo = agora
            self.tokens = min(self.capacidade, self.tokens + decorrido * self.taxa)

            if self.tokens < tokens:
                necessario = tokens - self.tokens
                espera = necessario / self.taxa
                if self.jitter_max > 0:
                    espera += random.uniform(0, self.jitter_max)
                time.sleep(espera)
                self.ultimo = time.monotonic()
                self.tokens = 0.0
            else:
                self.tokens -= tokens

    def registrar(self) -> None:
        with self._lock:
            self.ultimo = time.monotonic()
