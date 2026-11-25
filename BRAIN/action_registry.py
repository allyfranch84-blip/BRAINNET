"""
action_registry.py

Registro central de ações da BRAINNET.

Toda ação executável pela IA deve ser registrada aqui.

Exemplo:

registry.register(
    Action(
        name="open_app",
        handler=open_app,
        rollback=close_app
    )
)

registry.execute("open_app", mission)

"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Dict, Any, List
import traceback
import time


# ============================================================
# ACTION
# ============================================================

@dataclass
class Action:

    name: str

    handler: Callable[..., Any]

    rollback: Optional[Callable[..., Any]] = None

    description: str = ""

    tags: List[str] = field(default_factory=list)

    dangerous: bool = False

    enabled: bool = True


# ============================================================
# RESULT
# ============================================================

@dataclass
class ActionResult:

    action: str

    success: bool

    elapsed: float

    output: Any = None

    error: Optional[str] = None

    traceback: Optional[str] = None


# ============================================================
# REGISTRY
# ============================================================

class ActionRegistry:

    def __init__(self):

        self._actions: Dict[str, Action] = {}

        self.history: List[ActionResult] = []

    # --------------------------------------------------------

    def register(self, action: Action):

        if action.name in self._actions:

            raise ValueError(
                f"Ação já registrada: {action.name}"
            )

        self._actions[action.name] = action

    # --------------------------------------------------------

    def unregister(self, name: str):

        self._actions.pop(name, None)

    # --------------------------------------------------------

    def exists(self, name: str) -> bool:

        return name in self._actions

    # --------------------------------------------------------

    def get(self, name: str) -> Action:

        if name not in self._actions:

            raise KeyError(name)

        return self._actions[name]

    # --------------------------------------------------------

    def list_actions(self):

        return sorted(self._actions.keys())

    # --------------------------------------------------------

    def search(self, tag: str):

        results = []

        for action in self._actions.values():

            if tag in action.tags:

                results.append(action)

        return results

    # --------------------------------------------------------

    def execute(self, name: str, *args, **kwargs):

        action = self.get(name)

        if not action.enabled:

            raise RuntimeError(
                f"Ação '{name}' desabilitada."
            )

        start = time.perf_counter()

        try:

            output = action.handler(*args, **kwargs)

            elapsed = time.perf_counter() - start

            result = ActionResult(

                action=name,

                success=True,

                elapsed=elapsed,

                output=output

            )

        except Exception as exc:

            elapsed = time.perf_counter() - start

            result = ActionResult(

                action=name,

                success=False,

                elapsed=elapsed,

                error=str(exc),

                traceback=traceback.format_exc()

            )

        self.history.append(result)

        return result

    # --------------------------------------------------------

    def rollback(self, name: str, *args, **kwargs):

        action = self.get(name)

        if action.rollback is None:

            return False

        action.rollback(*args, **kwargs)

        return True

    # --------------------------------------------------------

    def enable(self, name: str):

        self.get(name).enabled = True

    # --------------------------------------------------------

    def disable(self, name: str):

        self.get(name).enabled = False

    # --------------------------------------------------------

    def clear_history(self):

        self.history.clear()

    # --------------------------------------------------------

    def statistics(self):

        total = len(self.history)

        success = sum(
            r.success for r in self.history
        )

        failed = total - success

        return {

            "registered": len(self._actions),

            "executed": total,

            "success": success,

            "failed": failed

        }


# ============================================================
# GLOBAL REGISTRY
# ============================================================

registry = ActionRegistry()


# ============================================================
# DECORATOR
# ============================================================

def action(

    name=None,

    rollback=None,

    description="",

    tags=None,

    dangerous=False

):

    tags = tags or []

    def decorator(func):

        registry.register(

            Action(

                name=name or func.__name__,

                handler=func,

                rollback=rollback,

                description=description,

                tags=tags,

                dangerous=dangerous

            )

        )

        return func

    return decorator