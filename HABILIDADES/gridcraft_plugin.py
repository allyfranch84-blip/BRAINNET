"""
AI OS v7 - Plugin / Habilidade: habilidade_gridcraft_excel.py
Localização: HABILIDADES/habilidade_gridcraft_excel.py
Especialidade: Automação Desktop do GridCraft/Excel e Engenharia de Datasets para IA
Ambiente Alvo: Windows 11 LTSC (Python 3.12)
"""

from __future__ import annotations

import asyncio
import ctypes
from ctypes import wintypes
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# Tentativa de importação da suíte profissional de planilhas
try:
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, NamedStyle, PatternFill, Side
    from openpyxl.utils import get_column_letter
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

# ==============================================================================
# CONFIGURAÇÃO DE METADADOS DO PLUGIN (COMPATIBILIDADE SKILL_LOADER AIOS v7)
# ==============================================================================

METADATA: Dict[str, Any] = {
    "name": "habilidade_gridcraft_excel",
    "version": "1.0.0",
    "description": (
        "Automação do GridCraft/Excel com capacidade de inicialização, primeiro plano "
        "e geração de planilhas profissionais estruturadas como datasets de treino de IA."
    ),
    "author": "AIOS v7 Core Team",
    "tags": [
        "gridcraft",
        "excel",
        "dataset",
        "ai_training",
        "desktop_automation",
        "spreadsheet_engineering",
    ],
    "triggers": [
        "abrir gridcraft",
        "iniciar gridcraft",
        "criar planilha de ia",
        "gerar dataset",
        "estruturar dataset excel",
        "planilha gridcraft treinamento",
        "exportar dataset profissional",
    ],
    "is_async": True,
}

# Win32 Native APIs
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

SW_RESTORE = 9
SW_SHOW = 5
SW_SHOWMAXIMIZED = 3

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL

user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL

user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int

user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL

user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL

user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL


# ==============================================================================
# MÓDULO 1: AUTOMAÇÃO E LOCALIZAÇÃO DO GRIDCRAFT / EXCEL
# ==============================================================================

class GridCraftAutomator:
    """Gerenciador de descoberta, lançamento e foco de janela do GridCraft / Excel."""

    SEARCH_PATHS = [
        Path(r"C:\ProgramFiles\GridCraft\GridCraft.exe"),
        Path(r"C:\Program Files\GridCraft\GridCraft.exe"),
        Path(r"C:\Program Files (x86)\GridCraft\GridCraft.exe"),
        Path(os.path.expandvars(r"%LOCALAPPDATA%\Programs\GridCraft\GridCraft.exe")),
        Path(r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE"),
        Path(r"C:\Program Files (x86)\Microsoft Office\root\Office16\EXCEL.EXE"),
    ]

    START_MENU_DIRS = [
        Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"),
        Path(os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")),
    ]

    @classmethod
    def find_executable(cls) -> Optional[Path]:
        """Procura o executável do GridCraft nas rotas primárias e atalhos do Menu Iniciar."""
        for path in cls.SEARCH_PATHS:
            if path.exists() and path.is_file():
                return path

        for base_dir in cls.START_MENU_DIRS:
            if base_dir.exists():
                for lnk in base_dir.rglob("*.lnk"):
                    name_lower = lnk.name.lower()
                    if "gridcraft" in name_lower or "excel" in name_lower:
                        return lnk
        return None

    @classmethod
    def find_window_by_title_keyword(cls, keyword: str) -> Optional[int]:
        """Varre janelas ativas à procura de títulos compatíveis com GridCraft/Excel."""
        matching_hwnd: List[int] = []

        def enum_handler(hwnd: int, _: int) -> bool:
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    if keyword.lower() in buf.value.lower():
                        matching_hwnd.append(hwnd)
                        return False
            return True

        user32.EnumWindows(WNDENUMPROC(enum_handler), 0)
        return matching_hwnd[0] if matching_hwnd else None

    @classmethod
    def bring_to_foreground(cls, hwnd: int) -> bool:
        """Restaura e força o foco da janela para permitir interação imediata."""
        if not hwnd:
            return False
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.BringWindowToTop(hwnd)
        return bool(user32.SetForegroundWindow(hwnd))

    @classmethod
    async def launch_and_focus(cls, target_file: Optional[Path] = None, timeout_sec: float = 6.0) -> Dict[str, Any]:
        """Executa a aplicação, abre o arquivo alvo e garante primeiro plano com telemetria."""
        t0 = time.perf_counter_ns()
        exe_path = cls.find_executable()

        cmd: List[str] = []
        if exe_path:
            cmd.append(str(exe_path))
            if target_file and target_file.exists():
                cmd.append(str(target_file))
            subprocess.Popen(cmd, shell=False)
        else:
            if target_file and target_file.exists():
                os.startfile(str(target_file))
            else:
                return {
                    "success": False,
                    "error": "Executável ou atalho do GridCraft não localizado no sistema.",
                    "latency_ms": (time.perf_counter_ns() - t0) / 1_000_000,
                }

        # Polling assíncrono para captura da janela em primeiro plano
        deadline = time.time() + timeout_sec
        hwnd = None
        keywords = ["GridCraft", "Excel", target_file.stem if target_file else "GridCraft"]

        while time.time() < deadline:
            for kw in keywords:
                hwnd = cls.find_window_by_title_keyword(kw)
                if hwnd:
                    break
            if hwnd:
                cls.bring_to_foreground(hwnd)
                break
            await asyncio.sleep(0.25)

        elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000
        return {
            "success": hwnd is not None,
            "hwnd": hwnd or 0,
            "executable": str(exe_path) if exe_path else "system_associated_handler",
            "file_opened": str(target_file) if target_file else None,
            "latency_ms": elapsed_ms,
        }


# ==============================================================================
# MÓDULO 2: GERADOR DE DATASETS DE TREINAMENTO E PLANILHAS PROFISSIONAIS
# ==============================================================================

class AIDatasetWorkbookBuilder:
    """Sintetizador profissional de planilhas com arquitetura de datasets para IA."""

    DOMAINS = ["desktop_automation", "system_diagnosis", "code_refactor", "spatial_reasoning", "db_optimization"]
    MODELS = ["qwen2.5-1.5b", "qwen2.5-7b"]
    PROMPTS_POOL = [
        ("Mapear coordenadas do botão Salvar e acionar clique em Q1", "desktop_automation", 0.28, 45),
        ("Analisar despejo de memória do processo aios_core1 e otimizar buffers", "system_diagnosis", 0.78, 120),
        ("Refatorar query SQL em SQLite WAL com junção hash e índice cobridor", "db_optimization", 0.85, 140),
        ("Mover cursor para 650, 500 e validar dHash do quadrante", "spatial_reasoning", 0.32, 55),
        ("Sintetizar pipeline assíncrono para processar telemetria de 60Hz", "code_refactor", 0.65, 95),
        ("Verificar status da janela em primeiro plano via GetForegroundWindow", "desktop_automation", 0.15, 30),
        ("Derivar formula de Fourier Holographic Reduced Representations 10000D", "system_diagnosis", 0.92, 180),
        ("Executar clique rápido de Sistema 1 no elemento gridcraft_cell_A1", "desktop_automation", 0.22, 40),
    ]

    @classmethod
    def _create_csv_fallback(cls, output_path: Path, num_rows: int) -> Path:
        """Gera versão CSV estruturada caso openpyxl não esteja instalado."""
        headers = [
            "sample_id", "timestamp_iso", "input_prompt", "domain_category",
            "token_count", "entropy_rate", "target_model", "complexity_score",
            "split_partition", "target_label_latency_ms"
        ]
        lines = [",".join(headers)]
        random.seed(42)

        for i in range(1, num_rows + 1):
            seed = random.choice(cls.PROMPTS_POOL)
            p_split = "TRAIN" if i <= int(num_rows * 0.7) else ("VAL" if i <= int(num_rows * 0.85) else "TEST")
            comp = round(min(1.0, max(0.05, seed[2] + random.uniform(-0.08, 0.08))), 4)
            model = "qwen2.5-7b" if comp >= 0.50 else "qwen2.5-1.5b"
            lat = round(comp * 850.0 + random.uniform(15, 45), 2)
            row = [
                f"SAMP_{i:05d}",
                datetime.datetime.now(datetime.timezone.utc).isoformat(),
                f'"{seed[0]}"',
                seed[1],
                str(seed[3] + random.randint(-5, 15)),
                str(round(random.uniform(0.45, 0.95), 4)),
                model,
                str(comp),
                p_split,
                str(lat),
            ]
            lines.append(",".join(row))

        csv_path = output_path.with_suffix(".csv")
        csv_path.write_text("\n".join(lines), encoding="utf-8")
        return csv_path

    @classmethod
    def build_training_workbook(cls, output_path: Path, num_samples: int = 60) -> Path:
        """Constrói uma planilha .xlsx profissional completa com múltiplas abas, estilos e métricas."""
        if not OPENPYXL_AVAILABLE:
            return cls._create_csv_fallback(output_path, num_samples)

        wb = openpyxl.Workbook()

        # Paleta Corporativa Moderna (Slate / Dark Navy)
        HEADER_FILL = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        ZEBRA_FILL = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
        TRAIN_FILL = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
        VAL_FILL = PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid")
        TEST_FILL = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")

        FONT_HEADER = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
        FONT_TITLE = Font(name="Segoe UI", size=14, bold=True, color="0F172A")
        FONT_BODY = Font(name="Segoe UI", size=9, color="334155")
        FONT_MONO = Font(name="Consolas", size=9, color="0F172A")

        BORDER_THIN = Border(
            left=Side(style="thin", color="E2E8F0"),
            right=Side(style="thin", color="E2E8F0"),
            top=Side(style="thin", color="E2E8F0"),
            bottom=Side(style="thin", color="E2E8F0"),
        )

        ALIGN_CENTER = Alignment(horizontal="center", vertical="center")
        ALIGN_LEFT = Alignment(horizontal="left", vertical="center")
        ALIGN_RIGHT = Alignment(horizontal="right", vertical="center")

        # ----------------------------------------------------------------------
        # ABA 1: DATASET_TREINAMENTO_IA
        # ----------------------------------------------------------------------
        ws_data = wb.active
        ws_data.title = "DATASET_TREINAMENTO_IA"
        ws_data.views.sheetView[0].showGridLines = True

        headers = [
            ("ID Amostra", 14),
            ("Data/Hora UTC", 22),
            ("Prompt Entrada (Feature)", 42),
            ("Domínio", 20),
            ("Tokens", 12),
            ("Entropia", 12),
            ("Complexidade", 14),
            ("Rótulo Modelo (Target)", 20),
            ("Partição Split", 14),
            ("Latência Meta (ms)", 18),
        ]

        for col_idx, (header_text, width) in enumerate(headers, start=1):
            cell = ws_data.cell(row=1, column=col_idx, value=header_text)
            cell.font = FONT_HEADER
            cell.fill = HEADER_FILL
            cell.alignment = ALIGN_CENTER
            cell.border = BORDER_THIN
            col_letter = get_column_letter(col_idx)
            ws_data.column_dimensions[col_letter].width = width
        ws_data.row_dimensions[1].height = 28

        random.seed(2026)
        train_count, val_count, test_count = 0, 0, 0

        for r_idx in range(2, num_samples + 2):
            sample_num = r_idx - 1
            seed = random.choice(cls.PROMPTS_POOL)

            if sample_num <= int(num_samples * 0.70):
                split_tag = "TRAIN"
                train_count += 1
                split_fill = TRAIN_FILL
            elif sample_num <= int(num_samples * 0.85):
                split_tag = "VAL"
                val_count += 1
                split_fill = VAL_FILL
            else:
                split_tag = "TEST"
                test_count += 1
                split_fill = TEST_FILL

            complexity = round(min(1.0, max(0.08, seed[2] + random.uniform(-0.06, 0.06))), 4)
            target_model = "qwen2.5-7b" if complexity >= 0.50 else "qwen2.5-1.5b"
            tokens = seed[3] + random.randint(-4, 18)
            entropy = round(random.uniform(0.50, 0.98), 4)
            lat_meta = round((complexity * 720.0) + (tokens * 1.5) + random.uniform(10, 30), 2)
            ts = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=sample_num * 12)).strftime("%Y-%m-%d %H:%M:%S")

            row_data = [
                (f"SAMP-{sample_num:05d}", ALIGN_CENTER, FONT_MONO, None),
                (ts, ALIGN_CENTER, FONT_BODY, None),
                (seed[0], ALIGN_LEFT, FONT_BODY, None),
                (seed[1], ALIGN_CENTER, FONT_BODY, None),
                (tokens, ALIGN_RIGHT, FONT_MONO, "#,##0"),
                (entropy, ALIGN_RIGHT, FONT_MONO, "0.0000"),
                (complexity, ALIGN_RIGHT, FONT_MONO, "0.0000"),
                (target_model, ALIGN_CENTER, FONT_MONO, None),
                (split_tag, ALIGN_CENTER, FONT_HEADER if False else FONT_BODY, split_fill),
                (lat_meta, ALIGN_RIGHT, FONT_MONO, "#,##0.00"),
            ]

            is_even = (r_idx % 2 == 0)
            ws_data.row_dimensions[r_idx].height = 20

            for c_idx, (val, align, font, custom_fill) in enumerate(row_data, start=1):
                c = ws_data.cell(row=r_idx, column=c_idx, value=val)
                c.alignment = align
                c.font = font
                c.border = BORDER_THIN
                if custom_fill:
                    c.fill = custom_fill
                elif is_even:
                    c.fill = ZEBRA_FILL

        # ----------------------------------------------------------------------
        # ABA 2: RESUMO_E_DISTRIBUICAO
        # ----------------------------------------------------------------------
        ws_meta = wb.create_sheet(title="RESUMO_E_DISTRIBUICAO")
        ws_meta.views.sheetView[0].showGridLines = True

        ws_meta.cell(row=2, column=2, value="AI OS v7 - Especificação do Dataset de Treino").font = FONT_TITLE
        ws_meta.row_dimensions[2].height = 24

        meta_rows = [
            ("Propósito", "Treinamento Supervisionado para Roteador Cognitivo (Router System 1 / 2)"),
            ("Total de Amostras Sintetizadas", num_samples),
            ("Amostras Treino (TRAIN ~70%)", train_count),
            ("Amostras Validação (VAL ~15%)", val_count),
            ("Amostras Teste (TEST ~15%)", test_count),
            ("Modelos Alvo", "Qwen2.5-1.5B (Fast-Path) | Qwen2.5-7B (Deep-Path)"),
            ("Data de Criação (UTC)", datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
            ("Compatibilidade", "GridCraft / Microsoft Excel 2016+ / LibreOffice"),
        ]

        for m_idx, (k, v) in enumerate(meta_rows, start=4):
            c_k = ws_meta.cell(row=m_idx, column=2, value=k)
            c_k.font = FONT_HEADER
            c_k.fill = HEADER_FILL
            c_k.border = BORDER_THIN
            c_k.alignment = ALIGN_LEFT

            c_v = ws_meta.cell(row=m_idx, column=3, value=v)
            c_v.font = FONT_BODY
            c_v.border = BORDER_THIN
            c_v.alignment = ALIGN_LEFT
            if m_idx % 2 == 0:
                c_v.fill = ZEBRA_FILL

        ws_meta.column_dimensions["B"].width = 30
        ws_meta.column_dimensions["C"].width = 65

        # ----------------------------------------------------------------------
        # ABA 3: DICIONARIO_DE_DADOS
        # ----------------------------------------------------------------------
        ws_dict = wb.create_sheet(title="DICIONARIO_DE_DADOS")
        ws_dict.views.sheetView[0].showGridLines = True

        dict_headers = ["Coluna", "Tipo Dado", "Definição Técnica", "Valores Permitidos / Exemplo"]
        for col_idx, h_name in enumerate(dict_headers, start=1):
            cell = ws_dict.cell(row=1, column=col_idx, value=h_name)
            cell.font = FONT_HEADER
            cell.fill = HEADER_FILL
            cell.alignment = ALIGN_CENTER
            cell.border = BORDER_THIN

        ws_dict.row_dimensions[1].height = 26
        ws_dict.column_dimensions["A"].width = 24
        ws_dict.column_dimensions["B"].width = 16
        ws_dict.column_dimensions["C"].width = 44
        ws_dict.column_dimensions["D"].width = 40

        dictionary_items = [
            ("ID Amostra", "STRING", "Identificador único da tupla de treino", "SAMP-00001 a SAMP-99999"),
            ("Data/Hora UTC", "DATETIME", "Momento exato da extração/síntese", "AAAA-MM-DD HH:MM:SS"),
            ("Prompt Entrada", "STRING", "Texto do comando fornecido pelo usuário/sistema", "Texto natural livre"),
            ("Domínio", "CATEGORICAL", "Contexto de execução operacional", ", ".join(cls.DOMAINS)),
            ("Tokens", "INTEGER", "Contagem aproximada de tokens de entrada", "1 a 4096"),
            ("Entropia", "FLOAT", "Taxa normalizada de densidade de informação Shannon", "0.0000 a 1.0000"),
            ("Complexidade", "FLOAT", "Score heurístico computado pelo ComplexityRouter", "0.0000 a 1.0000"),
            ("Rótulo Modelo", "CATEGORICAL", "Classe supervisionada para despacho", "qwen2.5-1.5b, qwen2.5-7b"),
            ("Partição Split", "CATEGORICAL", "Subdivisão do conjunto para validação cruzada", "TRAIN, VAL, TEST"),
            ("Latência Meta", "FLOAT", "SLA máximo para execução da inferência em ms", "Milissegundos (ex: 350.00)"),
        ]

        for r_idx, (col_n, t_n, desc_n, ex_n) in enumerate(dictionary_items, start=2):
            ws_dict.row_dimensions[r_idx].height = 20
            row_vals = [col_n, t_n, desc_n, ex_n]
            for c_idx, val in enumerate(row_vals, start=1):
                c = ws_dict.cell(row=r_idx, column=c_idx, value=val)
                c.font = FONT_MONO if c_idx in (1, 2, 4) else FONT_BODY
                c.border = BORDER_THIN
                c.alignment = ALIGN_CENTER if c_idx == 2 else ALIGN_LEFT
                if r_idx % 2 == 0:
                    c.fill = ZEBRA_FILL

        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(output_path))
        return output_path


# ==============================================================================
# MÓDULO 3: INTERFACE DE EXECUÇÃO PRINCIPAL DO PLUGIN (PADRÃO SKILL_LOADER)
# ==============================================================================

async def run(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """
    Ponto de Entrada Oficial para o AIOS v7.
    
    Parâmetros Suportados:
        action (str): 'generate_dataset' | 'launch_gridcraft' | 'full_pipeline' (padrão)
        samples (int): Quantidade de amostras no dataset (padrão: 60)
        output_dir (str): Diretório de destino do arquivo gerado
        filename (str): Nome do arquivo da planilha
        focus_app (bool): Se verdadeiro, força a inicialização e foco do GridCraft
    """
    t_start = time.perf_counter_ns()
    
    # Parâmetros de extração flexíveis
    action: str = kwargs.get("action", "full_pipeline")
    num_samples: int = int(kwargs.get("samples", 60))
    focus_app: bool = bool(kwargs.get("focus_app", True))
    
    # Resolução de diretórios
    default_dir = Path.home() / "Documents" / "AIOS_Datasets"
    target_dir = Path(kwargs.get("output_dir", default_dir))
    target_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    custom_filename = kwargs.get("filename")
    if custom_filename:
        file_path = target_dir / custom_filename
    else:
        file_path = target_dir / f"AIOS_TrainingDataset_{timestamp_str}.xlsx"

    results: Dict[str, Any] = {
        "plugin": METADATA["name"],
        "action": action,
        "status": "INITIALIZING",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "artifacts": {},
        "automation": {},
    }

    try:
        # 1. Geração da Planilha de Treino de IA
        if action in ("full_pipeline", "generate_dataset"):
            generated_file = await asyncio.to_thread(
                AIDatasetWorkbookBuilder.build_training_workbook,
                output_path=file_path,
                num_samples=num_samples,
            )
            results["artifacts"]["dataset_path"] = str(generated_file)
            results["artifacts"]["samples_count"] = num_samples
            results["artifacts"]["format"] = generated_file.suffix.replace(".", "").upper()

        # 2. Inicialização e Foco no GridCraft / Excel
        if action in ("full_pipeline", "launch_gridcraft") and focus_app:
            target_to_open = file_path if file_path.exists() else None
            auto_result = await GridCraftAutomator.launch_and_focus(target_file=target_to_open)
            results["automation"] = auto_result

        results["status"] = "SUCCESS"

    except Exception as ex:
        results["status"] = "ERROR"
        results["error_message"] = str(ex)

    total_latency_ms = (time.perf_counter_ns() - t_start) / 1_000_000
    results["total_latency_ms"] = round(total_latency_ms, 2)
    return results


async def execute(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """Alias para compatibilidade bidirecional com invocação de subclasses e PDAG Engine."""
    return await run(*args, **kwargs)


def run_sync(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """Fallback síncrono para execução direta fora de loops assíncronos."""
    return asyncio.run(run(*args, **kwargs))


# Registro dos atributos de introspecção do framework AIOS v7
setattr(run, "__aios_skill__", METADATA)
setattr(run, "__aios_skill_meta__", METADATA)
setattr(execute, "__aios_skill__", METADATA)
setattr(execute, "__aios_skill_meta__", METADATA)


if __name__ == "__main__":
    print("[AI OS v7] Iniciando teste autônomo de 'habilidade_gridcraft_excel'...")
    res = run_sync(action="full_pipeline", samples=50, focus_app=True)
    print(json.dumps(res, indent=2, ensure_ascii=False))