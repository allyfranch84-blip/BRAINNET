"""Collect decisions for the audited racing starter through the chat."""

import re
import threading
import unicodedata
from uuid import uuid4

from engineering_agent import ProjectBrief, run_racing_prototype


_PROJECT_REQUEST = re.compile(
    r"^(?:faca|faz|crie|cria|criar|crie pra mim|desenvolva|construa|quero(?: criar)?)"
    r" (?:um )?jogo (?:de |d )?cor+r?ida(?=\s|$)"
)
_PLATFORMS = {
    "navegador": "browser", "browser": "browser", "web": "browser",
    "windows": "windows", "pc": "windows", "desktop": "windows",
    "celular": "mobile", "android": "mobile", "ios": "mobile",
}
_FILLER = {"2d", "3d", "em", "no", "na", "para", "pra", "o", "a", "e", "sim", "pode", "ser"}
_DELEGATIONS = {"pode escolher", "escolha por mim", "use o padrao", "pode ser o padrao"}


def _normalize(text):
    unaccented = "".join(
        char for char in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(char)
    )
    return " ".join(unaccented.split()).strip(" .!")


def _choices(text):
    words = set(re.findall(r"[\w-]+", text))
    platforms = {_PLATFORMS[word] for word in words & _PLATFORMS.keys()}
    dimensions = words & {"2d", "3d"}
    understood = words <= _PLATFORMS.keys() | _FILLER
    return platforms, dimensions, understood


class ProjectConversation:
    """One pending brief per chat bridge, with no dispatch on unrelated turns."""

    def __init__(self, workspace):
        self._workspace = workspace
        self._lock = threading.Lock()
        self._brief = None
        self._project_id = None
        self._active = None

    def cancel(self):
        with self._lock:
            if self._active is not None:
                self._active.set()
                return "CANCEL_REQUESTED"
            if self._brief is not None:
                self._brief = None
                self._project_id = None
                return "CANCELLED"
            return "NO_PROJECT"

    def handle(self, text, *, cancelled):
        if len(text) > 1000:
            return None
        normalized = _normalize(text)
        if normalized == "/projeto cancelar":
            status = self.cancel()
            return {"status": status, "reply": {
                "CANCEL_REQUESTED": "Cancelamento solicitado ao executor do projeto.",
                "CANCELLED": "Projeto em esclarecimento cancelado.",
                "NO_PROJECT": "Nenhum projeto pendente.",
            }[status]}

        # A question, quotation or description must not open a project.
        request = _PROJECT_REQUEST.match(normalized) if "?" not in normalized else None
        explicit = normalized == "/projeto corrida"
        with self._lock:
            if request or explicit:
                if self._active is not None:
                    return {"status": "BUSY", "reply": "Já existe um projeto em execução nesta conversa."}
                self._project_id = uuid4().hex
                self._brief = ProjectBrief(text)
                answer = normalized[request.end():].strip(" ,") if request else ""
            elif self._brief is not None:
                answer = normalized
            else:
                return None

            platforms, dimensions, understood = _choices(answer)
            if answer in _DELEGATIONS:
                platforms = {"browser"}
                dimensions = {"2d"}
                understood = True
            if answer and not understood:
                if request or explicit:
                    return self._question("O protótipo local atende apenas aos requisitos de plataforma e dimensão. Confirme se quer começar pela versão mínima.")
                if platforms or dimensions:
                    return self._question("Identifiquei uma escolha e outros requisitos na mesma mensagem. Para começar pelo protótipo, confirme só a plataforma e se é 2D ou 3D.")
                return None
            if len(platforms) > 1 or len(dimensions) > 1:
                return self._question("Qual plataforma e dimensão você escolhe para a primeira versão?")

            self._brief = ProjectBrief(self._brief.goal,
                                       next(iter(platforms), self._brief.platform),
                                       next(iter(dimensions), self._brief.dimension))
            if self._brief.platform is None or self._brief.dimension is None:
                return self._question()
            if (self._brief.platform, self._brief.dimension) != ("browser", "2d"):
                return self._question("O executor disponível gera e verifica um jogo 2D de navegador. Você aceita essa primeira versão ou prefere cancelar?")

            brief, project_id = self._brief, self._project_id
            self._brief = self._project_id = None
            stop = self._active = threading.Event()
        try:
            result = run_racing_prototype(
                brief, workspace=self._workspace,
                cancelled=lambda: stop.is_set() or cancelled(),
            )
        finally:
            with self._lock:
                self._active = None
        if result["status"] == "GOAL_VERIFIED":
            reply = (
                f"Protótipo de corrida 2D criado e validado em {result['project_path']}.\n"
                "Abra index.html para jogar. O motor passou no Node.js em "
                + ", ".join(result["checks"]) + "."
            )
        else:
            detail = result.get("detail") or result["status"]
            reply = f"A validação do projeto ficou em {result['status']}. {detail}"
        return {"status": result["status"], "reply": reply, "project_id": project_id,
                "project_result": result, "sucesso_real": result["status"] == "GOAL_VERIFIED"}

    def _question(self, prefix=""):
        questions = []
        if self._brief.platform is None:
            questions.append("O jogo é para navegador, Windows ou celular?")
        if self._brief.dimension is None:
            questions.append("Você prefere 2D ou 3D?")
        reply = " ".join(part for part in (prefix, *questions) if part)
        if not prefix:
            reply += ' O protótipo disponível é 2D no navegador. Se quiser delegar, responda "pode escolher".'
        return {"status": "CLARIFICATION_REQUIRED", "reply": reply,
                "project_id": self._project_id, "sucesso_real": False}
