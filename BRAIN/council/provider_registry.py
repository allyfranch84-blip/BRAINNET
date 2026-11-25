# =============================================================================
# council/provider_registry.py — Registro de Provedores
# =============================================================================

from typing import Any, Dict, List

class ProviderRegistry:
    """Gerencia as portas (Chat, Browser, Test) disponíveis."""
    
    def __init__(self):
        self._providers: Dict[str, Any] = {}

    def register(self, name: str, provider: Any) -> None:
        self._providers[name] = provider

    def unregister(self, name: str) -> None:
        self._providers.pop(name, None)

    def exists(self, name: str) -> bool:
        return name in self._providers

    def get(self, name: str) -> Any:
        if not self.exists(name):
            raise ValueError(f"Provider '{name}' não registrado.")
        return self._providers[name]

    def list_all(self) -> List[str]:
        return list(self._providers.keys())