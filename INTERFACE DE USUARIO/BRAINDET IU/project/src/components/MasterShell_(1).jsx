/**
 * AI OS v7 — Master Shell · "Living Organism" v2 (React 18 + Tailwind 3.3+ + Framer Motion 11)
 *
 * O QUE MUDOU NESTA VERSÃO
 *   • GridCraft removido (Sub-GUI, registry e mock). Se o Kernel ainda listar "gridcraft",
 *     ele é ocultado no cliente por HIDDEN_SKILLS.
 *   • Home = tela de BLOCOS e PASTAS (herança Windows 8, versão vidro moderno):
 *       - blocos de tamanhos variados (1x1, 2x1, 2x2) com conteúdo "ao vivo"
 *       - pastas: habilidades com campo `folder` são agrupadas e abrem com transição
 *   • Tipografia cinética: títulos gigantes cujas letras entram em mola, "respiram" (peso variável)
 *     e reagem ao mouse. Texto contorno gigante deriva no fundo.
 *   • FOCO NO HOVER: o bloco sob o mouse cresce, inclina em 3D e recebe luz; os demais desfocam.
 *   • Barra de comando (omnibar) na home: digite sem sair da tela, a resposta aparece como balão.
 *   • Menu expansível com blocos quadrados e pastas recolhíveis. Atalho: tecla "M".
 *
 * CONTRATO COM O KERNEL (window.pywebview.api) — lado Python
 *   list_skills() -> [{id,name,icon,description,folder?}]   send_command(text) -> {reply, logs?:[{level,core,msg}]}
 *   run_skill(skill_id, action, payload) -> {ok, data?, log?}  set_voice(enabled) -> {ok}
 *   get_logs() -> [{level,core,msg}]                           set_theme("dark"|"light") -> None
 * Push Kernel -> UI (evaluate_js): CustomEvent 'aios:log' {level,core,msg} · 'aios:message' {role,text} · 'aios:skills' [..]
 *   'aios:schema' {title,subtitle,layout,widgets[],skill?}  — motor Auto-Gerador de UI (JSON declarativo)
 * send_command / run_skill podem devolver { schema } ou { data: { schema } } sem mudar a assinatura.
 * Ícones disponíveis para `icon`: home chat brain ai sun moon mic send plug terminal chevron menu search folder calendar file bolt back
 * Fora do PyWebView (npm run dev) um mock local é usado automaticamente.
 *
 * FONTES: usa Space Grotesk (variável) + JetBrains Mono via Google Fonts. Para rodar 100% offline no PyWebView:
 *   npm i @fontsource-variable/space-grotesk @fontsource-variable/jetbrains-mono  e importe no main.jsx.
 *   Sem elas, cai em Helvetica/Arial automaticamente.
 */
import React, { createContext, lazy, Suspense, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
const TelemetryDashboard = lazy(() => import("./TelemetryDashboard"));
import Hotbar from "./Hotbar";
import SemanticTrainer from "./SemanticTrainer";
import VoiceToast from "./VoiceToast";
import SendStopButton from "./SendStopButton";
import { useChatInputFocus, CopyButton, MessageActions, SearchButton } from "./ChatActions";
import { visibleChatMessages, chatHistoryText } from "./chatHistory.mjs";
import {
  AnimatePresence, motion, useMotionTemplate, useMotionValue, useReducedMotion, useSpring, useTransform,
} from "framer-motion";

/* ── 1. Física, tema, tipografia ───────────────────────────────── */
const SPRING = { type: "spring", stiffness: 140, damping: 20 };
const JELLY = { type: "spring", stiffness: 260, damping: 14 };
const MONO = { fontFamily: "'JetBrains Mono','Fira Code',ui-monospace,Menlo,monospace" };
const DISPLAY = "'Space Grotesk','Helvetica Neue',Helvetica,Arial,sans-serif";
const IRIS = "linear-gradient(120deg,#7ff0e0,#d29bff,#ff8fc0,#ffb27a,#7ff0e0)";
const IRIS_FILL = "linear-gradient(135deg,rgba(127,240,224,.92),rgba(210,155,255,.9) 38%,rgba(255,143,192,.88) 66%,rgba(255,226,122,.9))";
const HIDDEN_SKILLS = new Set(["gridcraft"]);
const cleanSkills = (arr) => arr.filter((s) => !HIDDEN_SKILLS.has(String(s.id).toLowerCase()));

/** Vidro temperado ultraleve — um único blur raso, sem saturate agressivo nem camadas empilhadas. */
const GLASS_FX = {
  background: "var(--glass)",
  backgroundImage: "linear-gradient(165deg, color-mix(in srgb, var(--spec) 42%, transparent) 0%, transparent 46%, color-mix(in srgb, var(--rim) 12%, transparent) 100%)",
  backdropFilter: "blur(10px) saturate(120%)",
  WebkitBackdropFilter: "blur(10px) saturate(120%)",
};
const ShellFxCtx = createContext({ lite: false });

const THEMES = {
  dark: {
    "--glass": "rgba(18,16,28,.38)", "--cell": "rgba(30,26,44,.85)", "--edge": "rgba(255,255,255,.10)",
    "--spec": "rgba(255,255,255,.22)", "--shadow": "rgba(0,0,0,.65)", "--glow": "rgba(140,230,255,.32)",
    "--cyan": "#7ff0e0", "--violet": "#d29bff", "--warm": "#ffb27a", "--rose": "#ff8fc0", "--rim": "#7ff0e0",
    "--text": "#f1f2ff", "--muted": "rgba(224,226,245,.56)", "--bubble-user": "rgba(210,155,255,.18)",
    "--chip": "rgba(255,255,255,.06)", "--err": "#ff6f8e", "--bg-a": "#0d0d14", "--bg-b": "#020204",
    "--smoke": "236,240,255", "--dots": "236,240,255",
  },
  light: {
    "--glass": "rgba(255,255,255,.34)", "--cell": "rgba(255,255,255,.88)", "--edge": "rgba(255,255,255,.75)",
    "--spec": "rgba(255,255,255,.95)", "--shadow": "rgba(50,56,70,.22)", "--glow": "rgba(60,230,140,.38)",
    "--cyan": "#0b9d6a", "--violet": "#7a5ce0", "--warm": "#e0803a", "--rose": "#d6508e", "--rim": "#2fe07a",
    "--text": "#14151b", "--muted": "rgba(20,21,27,.55)", "--bubble-user": "rgba(47,224,122,.18)",
    "--chip": "rgba(20,21,27,.05)", "--err": "#d63a5a", "--bg-a": "#eceef0", "--bg-b": "#c3c6cd",
    "--smoke": "14,14,20", "--dots": "20,22,34",
  },
};

/* ── 2. Bridge: window.pywebview.api (com mock) ────────────────── */
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
function extractSchema(payload) {
  if (!payload || typeof payload !== "object") return null;
  if (Array.isArray(payload.widgets) || payload.layout) return payload;
  if (payload.schema && typeof payload.schema === "object") return extractSchema(payload.schema);
  if (payload.data && typeof payload.data === "object") return extractSchema(payload.data);
  if (payload.ui && typeof payload.ui === "object") return extractSchema(payload.ui);
  return null;
}

const SAMPLE_SCHEMA = {
  title: "Painel de Controle de Exemplo",
  subtitle: "Gerado dinamicamente pelo Kernel",
  layout: "grid",
  skill: "ui",
  widgets: [
    { id: "w1", type: "metric", label: "VRAM em Uso", value: "2.4 GB", trend: "+12%" },
    { id: "w2", type: "toggle", label: "Isolamento Estrito", value: true, action: "toggle_sandbox" },
    { id: "w3", type: "button", label: "Purgar Memória Caótica", variant: "iris", action: "purge_cache", payload: { target: "all" } },
    { id: "w4", type: "slider", label: "Sensibilidade do Olho", min: 0, max: 100, value: 75, action: "set_sensitivity" },
    { id: "w5", type: "log_stream", label: "Feed Causal", lines: ["Sinal 01 ativo", "Sinapse mielinizada"] },
  ],
};
const mockApi = {
  async list_skills() {
    return [
      { id: "memory", name: "Memória", icon: "brain", description: "Contexto de longo prazo" },
      { id: "search", name: "Pesquisa", icon: "search", description: "Web e documentos", folder: "Ferramentas" },
      { id: "files", name: "Arquivos", icon: "file", description: "Pastas locais", folder: "Ferramentas" },
      { id: "calendar", name: "Agenda", icon: "calendar", description: "Compromissos", folder: "Ferramentas" },
      { id: "automations", name: "Automações", icon: "bolt", description: "Rotinas do Kernel" },
    ];
  },
  async get_logs() {
    return [
      { level: "INFO", core: "Core1", msg: "AI OS Core 1 Kernel online." },
      { level: "INFO", core: "Core1", msg: "Habilidades recarregadas (5 itens)." },
    ];
  },
  async send_command(text) {
    await wait(600);
    const wantsUi = /^\s*\/ui\b/i.test(text) || /\b(schema|painel|layout)\b/i.test(text);
    return {
      reply: wantsUi ? "[mock] Layout declarativo injetado pelo Kernel." : `[mock] Comando recebido: "${text}"`,
      logs: [{ level: "INFO", core: "Core1", msg: wantsUi ? "Schema UI despachado." : `Comando despachado: ${text}` }],
      schema: wantsUi ? SAMPLE_SCHEMA : undefined,
    };
  },
  async run_skill(id, action, payload) { await wait(350); return { ok: true, log: `[mock] ${id}.${action} executado`, data: payload || {} }; },
  async set_voice() { return { ok: true }; },
  async set_theme() {},
  async get_effort_mode() { return { ok: false, error: 'Kernel indisponível' }; },
  async set_effort_mode() { return { ok: false, error: 'Kernel indisponível' }; },
  async toggle_fullscreen() { return { ok: true }; },
  async set_widget_mode(enabled) { await wait(200); return { ok: true }; },
  async set_window_size(w, h) { await wait(150); return { ok: true }; },
  async set_window_position(x, y) { await wait(100); return { ok: true }; },
};

function useKernel() {
  const [bridge, setBridge] = useState(() => (window.pywebview?.api ? "pywebview" : "mock"));
  useEffect(() => {
    const onReady = () => setBridge("pywebview");
    window.addEventListener("pywebviewready", onReady);
    return () => window.removeEventListener("pywebviewready", onReady);
  }, []);
  const call = useCallback(async (method, ...args) => {
    const api = window.pywebview?.api;
    const target = bridge === "pywebview" ? api : mockApi;
    if (typeof target?.[method] !== 'function') return { ok: false, error: `Método ${method} indisponível` };
    try { return await target[method](...args); }
    catch (err) { console.error(`[kernel] ${method} falhou`, err); return { ok: false, error: String(err) }; }
  }, [bridge]);
  return { call, bridge };
}

/* ── 3. Ícones ─────────────────────────────────────────────────── */
const ICONS = {
  network: <><path d="M7 6 12 16 19 7M7 6l12 1" /><circle cx="6" cy="5" r="3" /><circle cx="12" cy="19" r="3" /><circle cx="20" cy="6" r="3" /></>,
  home: <path d="M3 11.5 12 4l9 7.5M5.5 10v9a1 1 0 0 0 1 1H10v-5h4v5h3.5a1 1 0 0 0 1-1v-9" />,
  chat: <><path d="M4 5h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1h-8l-5 4v-4H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z" /><path d="M8 10.5h.01M12 10.5h.01M16 10.5h.01" strokeWidth="2.4" /></>,
  brain: <><path d="M12 5v14" /><path d="M9.5 4A3 3 0 0 0 6.5 7a3 3 0 0 0-2 3 3 3 0 0 0 1 4 3 3 0 0 0 3 4.5h1" /><path d="M14.5 4a3 3 0 0 1 3 3 3 3 0 0 1 2 3 3 3 0 0 1-1 4 3 3 0 0 1-3 4.5h-1" /><path d="M9 9.5h1.5M13.5 12H15M9 14.5h1.5" /></>,
  ai: <><rect x="6" y="6" width="12" height="12" rx="4" /><path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3M9.5 15l2.5-6 2.5 6M10.4 13h3.2" /></>,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8" /></>,
  moon: <path d="M20 14.5A8.5 8.5 0 0 1 ... (truncated)