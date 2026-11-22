"""Calibracao por intencao a partir de resultados factuais, sem LLM."""
from dataclasses import dataclass
import math
from threading import Lock
from typing import Dict


@dataclass
class _Resultados:
    tentativas: int = 0
    acertos: int = 0
    soma_confianca: float = 0.0


class MetacognitionEngine:
    def __init__(self) -> None:
        self._resultados: Dict[str, _Resultados] = {}
        self._lock = Lock()

    @staticmethod
    def _chave(intencao: str) -> str:
        chave = " ".join(intencao.casefold().split())
        if not chave:
            raise ValueError("intencao nao pode ser vazia")
        return chave

    def registrar_resultado(self, intencao: str, confianca_alegada: float, sucesso_real: bool) -> float:
        """Registra uma tentativa e retorna E[hit] - E[conf] para a intencao."""
        chave = self._chave(intencao)
        confianca = float(confianca_alegada)
        if not math.isfinite(confianca) or not 0.0 <= confianca <= 1.0:
            raise ValueError("confianca_alegada deve estar entre 0 e 1")
        if not isinstance(sucesso_real, bool):
            raise TypeError("sucesso_real deve ser bool factual")
        with self._lock:
            resultado = self._resultados.setdefault(chave, _Resultados())
            resultado.tentativas += 1
            resultado.acertos += int(sucesso_real)
            resultado.soma_confianca += confianca
            return (resultado.acertos - resultado.soma_confianca) / resultado.tentativas

    def obter_status(self) -> Dict[str, float]:
        """Agrega apenas observacoes registradas, sem criar tentativas sinteticas."""
        with self._lock:
            n = sum(item.tentativas for item in self._resultados.values())
            hits = sum(item.acertos for item in self._resultados.values())
            confidence = sum(item.soma_confianca for item in self._resultados.values())
            return {"tentativas": n, "taxa_acerto": hits / n if n else 0.0,
                    "confianca_media": confidence / n if n else 0.0,
                    "erro_calibracao": (hits - confidence) / n if n else 0.0}

    def obter_calibracao(self, intencao: str) -> Dict[str, float]:
        chave = self._chave(intencao)
        with self._lock:
            resultado = self._resultados.get(chave, _Resultados())
            n = resultado.tentativas
            taxa_acerto = resultado.acertos / n if n else 0.0
            confianca_media = resultado.soma_confianca / n if n else 0.0
            return {
                "tentativas": n,
                "taxa_acerto": taxa_acerto,
                "confianca_media": confianca_media,
                "erro_calibracao": taxa_acerto - confianca_media,
            }
