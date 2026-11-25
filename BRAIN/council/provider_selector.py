# =============================================================================
# council/provider_selector.py — Roteador de Papéis para Modelos
# =============================================================================

from enum import Enum

class Role(str, Enum):
    ARCHITECT = "architect"
    IMPLEMENTER = "implementer"
    REVIEWER = "reviewer"

class ProviderSelector:
    """Decide qual modelo assume qual papel, sem que o Planner saiba."""
    
    def __init__(self):
        # Mapeamento padrão. Pode ser alterado via config ou heurística.
        self._mapping = {
            Role.ARCHITECT: "chatgpt",
            Role.IMPLEMENTER: "deepseek",
            Role.REVIEWER: "chatgpt"
        }

    def resolve(self, role: Role) -> str:
        """Retorna o nome do provider (ex: 'chatgpt') para o papel (ex: 'architect')."""
        return self._mapping.get(role, "deepseek")

    def override(self, role: Role, provider_name: str) -> None:
        """Permite trocar o modelo de um papel em tempo de execução."""
        self._mapping[role] = provider_name