"""Literal OS launch intents. No fuzzy app substitution and no side effects."""
import re

PHYSICAL = r"\b(?:arm[aá]rio|papel|geladeira|boca|chuveiro|torneira|sof[aá]|cama|luz|l[aâ]mpada|mesa|cadeira|copo|prato|garfo|faca|panela|fog[aã]o|micro-ondas|tv|televis[aã]o|ventilador|ar-condicionado)\b"

def is_unqualified_physical_door(text):
    return bool(re.fullmatch(r'\s*(?:abra|abre|abrir|inicie)\s+(?:a\s+)?porta\s*[.!]?\s*', str(text), re.I))


def app_process_names(target):
    name = str(target).casefold().removesuffix(".exe").strip()
    name = {"bloco de notas": "notepad", "editor de texto": "notepad", "calculadora": "calc", "paint": "mspaint", "krita": "krita", "lightroom": "lightroom"}.get(name, name)
    roots = {"calc", "calculator", "calculatorapp"} if name == "calc" else {name}
    return {variant for root in roots for variant in (root, root + ".exe")}


def find_app_window_by_title(target):
    """Read-only fallback for visible Calculator UWP top-level windows."""
    import win32gui
    import win32process
    name = str(target).casefold().removesuffix(".exe").strip()
    if name not in ("calc", "calculator", "calculatorapp", "calculadora"):
        return None
    matches = []
    def inspect(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if any(word in title.casefold() for word in ("calculadora", "calculator")):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            matches.append({"hwnd": hwnd, "pid": pid, "title": title})
    win32gui.EnumWindows(inspect, None)
    return matches[0] if matches else None


def hosted_app_window(target, hwnd=None):
    """Bind a generic UWP frame to its app through child HWND owners, not titles."""
    import psutil
    import win32gui
    import win32process
    names, found = app_process_names(target), []
    def inspect(frame, _):
        if not win32gui.IsWindow(frame):
            return
        _, host_pid = win32process.GetWindowThreadProcessId(frame)
        try:
            if psutil.Process(host_pid).name().casefold() != "applicationframehost.exe":
                return
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return
        def child(candidate, _):
            _, pid = win32process.GetWindowThreadProcessId(candidate)
            try:
                name = psutil.Process(pid).name().casefold()
                if name in names and psutil.pid_exists(pid):
                    found.append({"pid": host_pid, "process_name": "applicationframehost.exe", "hwnd": frame,
                                  "app_pid": pid, "app_process_name": name})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return
        win32gui.EnumChildWindows(frame, child, None)
    if hwnd:
        inspect(hwnd, None)
    else:
        win32gui.EnumWindows(inspect, None)
    return found[0] if found else None


def find_app_process(target):
    import psutil
    if not target:
        return None
    names = app_process_names(target)
    hosts = False
    for process in psutil.process_iter(["pid", "name"]):
        try:
            hosts = hosts or str(process.info.get("name", "")).casefold() == "applicationframehost.exe"
            if str(process.info.get("name", "")).casefold() in names and psutil.pid_exists(process.info["pid"]) and process.status() not in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD):
                return {"pid": process.info["pid"], "process_name": process.info["name"]}
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return hosted_app_window(target) if hosts else None


def has_system_terms(text):
    text = str(text).casefold()
    return bool(re.search(r"menu iniciar|start menu|gridcraft|pesquise no pc|(?:^|\b)(?:abra|abre|abrir|inicie|execute)\s", text))


def is_web_navigation(text):
    text = str(text).casefold()
    return bool(re.search(r"\b(?:brave|thorium|chrome|edge|navegador)\b", text)
                and re.search(r"\b(?:pesquise|pesquisar|busque|buscar)\b", text)
                and not re.search(r"menu iniciar|start menu|no pc|no computador", text))


def system_launch_target(text):
    text = " ".join(str(text).strip().split())
    if re.search(PHYSICAL, text, re.I) or is_unqualified_physical_door(text):
        return None
    if re.search(r"menu iniciar|start menu", text, re.I):
        match = re.search(r"\b(?:digite|escreva|pesquise|procure|busque)\s+(?:por\s+)?(.+)", text, re.I)
    else:
        match = re.match(r"^(?:(?:abra|abre|abrir|inicie|execute|feche|fechar|encerre|encerrar|mate|matar|finalize|minimize|minimizar|maximize|maximizar|restaure|restaurar)\s+(?:(?:o|a)\s+)?|(?:pesquise|procure|busque)\s+no\s+(?:pc|computador)\s+(?:por\s+)?)(.+)", text, re.I)
    if not match:
        return None
    target = match.group(1).strip()
    quoted = re.match(r'''^["'“](.+?)["'”]''', target)
    if quoted:
        target = quoted.group(1)
    else:
        target = re.split(r"\s+e\s+|\s+(?:aperte|pressione|tecle)\b|[;…]", target, maxsplit=1, flags=re.I)[0]
    target = target.strip(" .,!?:'\"“”")
    if not target or len(target) > 120 or target.casefold() in ("isso", "aquilo", "algo", "alguma coisa", "processo", "aplicativo", "app", "programa", "menu iniciar"):
        return None
    if re.search(r"[<>|`\r\n]", target):
        return None
    target = target.casefold()
    return {"note pad": "notepad"}.get(target, target)


def application_matches(target, process_name, title):
    target = str(target).casefold().removesuffix(".exe").strip()
    process = str(process_name).casefold().removesuffix(".exe")
    if not target:
        return False
    if process in ("searchhost", "searchapp", "startmenuexperiencehost"):
        return False
    if any(name in process for name in ("whatsapp", "discord", "telegram")) and target not in process:
        return False
    aliases = {"bloco de notas": "notepad", "editor de texto": "notepad"}
    if process == aliases.get(target, target):
        return True
    titles = [target, "bloco de notas"] if target == "notepad" else [target]
    return any(re.search(r"(?:^|[-—–|]\s*)" + re.escape(name) + r"(?:\s*[-—–|]|$)", str(title).casefold()) for name in titles)
