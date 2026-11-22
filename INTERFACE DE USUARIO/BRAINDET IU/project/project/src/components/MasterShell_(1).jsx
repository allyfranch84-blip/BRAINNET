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
 * Ícones disponíveis para `icon`: home chat brain ai sun moon mic send plug terminal chevron menu search folder calendar file bolt back
 * Fora do PyWebView (npm run dev) um mock local é usado automaticamente.
 *
 * FONTES: usa Space Grotesk (variável) + JetBrains Mono via Google Fonts. Para rodar 100% offline no PyWebView:
 *   npm i @fontsource-variable/space-grotesk @fontsource-variable/jetbrains-mono  e importe no main.jsx.
 *   Sem elas, cai em Helvetica/Arial automaticamente.
 */
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
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
    return { reply: `[mock] Comando recebido: "${text}"`, logs: [{ level: "INFO", core: "Core1", msg: `Comando despachado: ${text}` }] };
  },
  async run_skill(id, action) { await wait(350); return { ok: true, log: `[mock] ${id}.${action} executado` }; },
  async set_voice() { return { ok: true }; },
  async set_theme() {},
  async get_effort_mode() { return { ok: false, error: "Kernel indisponível" }; },
  async set_effort_mode() { return { ok: false, error: "Kernel indisponível" }; },
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
    const target = bridge === "pywebview" && api?.[method] ? api : mockApi;
    try { return await target[method](...args); }
    catch (err) { console.error(`[kernel] ${method} falhou`, err); return { ok: false, error: String(err) }; }
  }, [bridge]);
  return { call, bridge };
}

/* ── 3. Ícones ─────────────────────────────────────────────────── */
const ICONS = {
  home: <path d="M3 11.5 12 4l9 7.5M5.5 10v9a1 1 0 0 0 1 1H10v-5h4v5h3.5a1 1 0 0 0 1-1v-9" />,
  chat: <><path d="M4 5h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1h-8l-5 4v-4H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z" /><path d="M8 10.5h.01M12 10.5h.01M16 10.5h.01" strokeWidth="2.4" /></>,
  brain: <><path d="M12 5v14" /><path d="M9.5 4A3 3 0 0 0 6.5 7a3 3 0 0 0-2 3 3 3 0 0 0 1 4 3 3 0 0 0 3 4.5h1" /><path d="M14.5 4a3 3 0 0 1 3 3 3 3 0 0 1 2 3 3 3 0 0 1-1 4 3 3 0 0 1-3 4.5h-1" /><path d="M9 9.5h1.5M13.5 12H15M9 14.5h1.5" /></>,
  ai: <><rect x="6" y="6" width="12" height="12" rx="4" /><path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3M9.5 15l2.5-6 2.5 6M10.4 13h3.2" /></>,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8" /></>,
  moon: <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" />,
  mic: <><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3" /></>,
  send: <path d="M21 3 10 14M21 3l-7 18-4-7-7-4 18-7Z" />,
  plug: <path d="M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0V8ZM12 17v4" />,
  terminal: <path d="m4 7 5 5-5 5M12 18h8" />,
  chevron: <path d="m6 9 6 6 6-6" />,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  search: <><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4-4" /></>,
  folder: <path d="M3.5 7.5a2 2 0 0 1 2-2H10l2 2.5h6.5a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2V7.5Z" />,
  calendar: <><rect x="3.5" y="5" width="17" height="15" rx="3" /><path d="M3.5 10h17M8 3v4M16 3v4" /></>,
  file: <><path d="M7 3.5h7l4 4V19a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 6 19V5A1.5 1.5 0 0 1 7 3.5Z" /><path d="M14 3.5V8h4M9 13h6M9 16h4" /></>,
  bolt: <path d="M13 2.5 5 13.5h6l-1 8 8-11h-6l1-8Z" />,
  back: <path d="M10 6 4 12l6 6M4 12h16" />,
  maximize: <><path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3" /></>,
  minimize: <><path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3" /><path d="M9 12h6" strokeWidth="2" /></>,
  widget: <><rect x="3" y="3" width="8" height="8" rx="2" /><rect x="13" y="3" width="8" height="5" rx="2" /><rect x="13" y="11" width="8" height="10" rx="2" /><rect x="3" y="14" width="8" height="7" rx="2" /></>,
  bell: <><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" /></>,
  grip: <><circle cx="9" cy="6" r="1.3" /><circle cx="15" cy="6" r="1.3" /><circle cx="9" cy="12" r="1.3" /><circle cx="15" cy="12" r="1.3" /><circle cx="9" cy="18" r="1.3" /><circle cx="15" cy="18" r="1.3" /></>,
  close: <path d="M6 6l12 12M18 6 6 18" />,
};
function Icon({ name, className = "w-6 h-6", ...rest }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true" {...rest}>
      {ICONS[name] ?? ICONS.plug}
    </svg>
  );
}

/* ── 4. Utilidades ─────────────────────────────────────────────── */
const rng = (seed) => { let s = seed >>> 0; return () => (s = (s * 1664525 + 1013904223) >>> 0) / 4294967296; };
const smooth = (pts) => {
  let d = `M${pts[0][0]} ${pts[0][1]}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const [x, y] = pts[i]; const [nx, ny] = pts[i + 1];
    d += ` Q${x} ${y} ${(x + nx) / 2} ${(y + ny) / 2}`;
  }
  const l = pts[pts.length - 1];
  return `${d} L${l[0]} ${l[1]}`;
};
const GRAIN = `url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='140' height='140'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='2'/><feColorMatrix values='0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 .6 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>")`;

function useClock() {
  const [d, setD] = useState(() => new Date());
  useEffect(() => { const t = setInterval(() => setD(new Date()), 1000); return () => clearInterval(t); }, []);
  return d;
}
const greet = (h) => (h < 5 ? "boa madrugada" : h < 12 ? "bom dia" : h < 18 ? "boa tarde" : "boa noite");

/** Número que deriva devagar, como leitura de um organismo. */
function Readout({ base = 1134.254, drift = 40, digits = 3, className = "" }) {
  const reduce = useReducedMotion();
  const [v, setV] = useState(base);
  useEffect(() => {
    if (reduce) return undefined;
    const t = setInterval(() => setV(base + (Math.random() - 0.5) * drift), 1400);
    return () => clearInterval(t);
  }, [base, drift, reduce]);
  return (
    <motion.span key={v.toFixed(digits)} initial={reduce ? false : { opacity: 0.3 }} animate={{ opacity: 1 }} transition={{ duration: 0.7 }} className={className} style={MONO}>
      {v.toFixed(digits)}
    </motion.span>
  );
}

/** Linha que troca de texto com rolagem vertical (conteúdo "ao vivo" dos blocos). */
function LiveLine({ lines, every = 3400, className = "", style }) {
  const [i, setI] = useState(0);
  const n = lines.length;
  useEffect(() => {
    if (n < 2) return undefined;
    const t = setInterval(() => setI((x) => (x + 1) % n), every);
    return () => clearInterval(t);
  }, [n, every]);
  if (!n) return null;
  return (
    <span className={`relative block h-[1.5em] overflow-hidden ${className}`} style={style}>
      <AnimatePresence mode="wait" initial={false}>
        <motion.span key={i % n} className="block truncate" initial={{ y: "100%", opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: "-100%", opacity: 0 }} transition={SPRING}>
          {lines[i % n]}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}

/** Tipografia cinética: letras entram em mola, respiram (peso variável) e reagem ao mouse. */
function Kinetic({ text, size = "clamp(56px,8.5vw,132px)", weight = 300, delay = 0, className = "" }) {
  const reduce = useReducedMotion();
  return (
    <span className={`inline-flex flex-wrap ${className}`} style={{ fontFamily: DISPLAY, fontSize: size, lineHeight: 0.95, letterSpacing: "-0.045em" }} aria-label={text}>
      {[...text].map((ch, i) => (ch === " "
        ? <span key={`${text}-${i}`} aria-hidden style={{ display: "inline-block", width: "0.28em" }} />
        : (
          <motion.span key={`${text}-${i}`} aria-hidden className="inline-block cursor-default transition-colors duration-300 hover:[color:var(--cyan)]"
            initial={{ y: "0.45em", opacity: 0, filter: "blur(12px)", rotate: 6 }} animate={{ y: 0, opacity: 1, filter: "blur(0px)", rotate: 0 }}
            transition={{ ...SPRING, delay: delay + i * 0.045 }} whileHover={{ y: -10, scale: 1.14, skewX: -10, transition: JELLY }}>
            <motion.span className="inline-block" style={{ fontWeight: weight }} animate={reduce ? undefined : { fontWeight: [weight, weight + 350, weight] }}
              transition={{ duration: 5, repeat: Infinity, delay: i * 0.18, ease: "easeInOut" }}>{ch}</motion.span>
          </motion.span>
        )))}
    </span>
  );
}

/* ── 5. Atmosfera: tipografia gigante, fumaça, terreno de pontos, esferas, chips holo ─ */
function SvgDefs() {
  return (
    <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden>
      <defs>
        <filter id="aios-smoke" x="-20%" y="-20%" width="140%" height="140%">
          <feTurbulence type="fractalNoise" baseFrequency="0.006 0.011" numOctaves="3" seed="4" result="n" />
          <feDisplacementMap in="SourceGraphic" in2="n" scale="150" xChannelSelector="R" yChannelSelector="G" />
        </filter>
        <filter id="aios-smoke-s" x="-20%" y="-20%" width="140%" height="140%">
          <feTurbulence type="fractalNoise" baseFrequency="0.012 0.02" numOctaves="3" seed="9" result="n" />
          <feDisplacementMap in="SourceGraphic" in2="n" scale="70" xChannelSelector="R" yChannelSelector="G" />
        </filter>
      </defs>
    </svg>
  );
}

function Smoke({ count = 6, intensity = 1, seed = 1, soft = false, className = "" }) {
  const reduce = useReducedMotion();
  const puffs = useMemo(() => {
    const r = rng(seed * 13 + 5);
    return Array.from({ length: count }, () => ({ x: r() * 78 + 4, s: 220 + r() * 300, d: 16 + r() * 16, delay: r() * 12, o: 0.22 + r() * 0.26 }));
  }, [count, seed]);
  return (
    <div aria-hidden className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`} style={{ filter: `url(#${soft ? "aios-smoke-s" : "aios-smoke"})` }}>
      {puffs.map((p, i) => (
        <motion.span key={i} className="absolute rounded-full"
          style={{ left: `${p.x}%`, bottom: "-25%", width: p.s, height: p.s, filter: "blur(14px)",
                   background: `radial-gradient(closest-side,rgba(var(--smoke),${p.o * intensity}),rgba(var(--smoke),${p.o * intensity * 0.4}) 45%,transparent 72%)` }}
          initial={{ opacity: reduce ? 0.3 : 0 }}
          animate={reduce ? undefined : { y: ["0%", "-150%", "-320%"], x: [0, 40, -30], scale: [0.7, 1.2, 1.8], opacity: [0, 1, 0] }}
          transition={{ duration: p.d, repeat: Infinity, ease: "easeOut", delay: p.delay }} />
      ))}
    </div>
  );
}

function DotTerrain() {
  const ref = useRef(null);
  const reduce = useReducedMotion();
  useEffect(() => {
    const c = ref.current;
    if (!c) return undefined;
    const ctx = c.getContext("2d");
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    let raf; let t = 0; let w = 0; let h = 0;
    const COLS = 84; const ROWS = 34;
    const resize = () => { w = c.clientWidth; h = c.clientHeight; c.width = w * dpr; c.height = h * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); };
    const draw = () => {
      const rgb = getComputedStyle(c).getPropertyValue("--dots").trim() || "236,240,255";
      ctx.clearRect(0, 0, w, h);
      for (let iz = 0; iz < ROWS; iz++) {
        const z = iz / (ROWS - 1);
        for (let ix = 0; ix < COLS; ix++) {
          const u = ix / (COLS - 1);
          const hg = Math.sin(ix * 0.23 + t * 0.7 + iz * 0.15) * Math.cos(iz * 0.31 - t * 0.5) * 26 + Math.sin(ix * 0.09 - t * 0.4 + iz * 0.22) * 34;
          const x = (u - 0.5) * w * 1.25 + w / 2;
          const y = h * 0.62 + z * h * 0.38 - hg * (0.4 + z * 0.9);
          const a = (0.08 + z * 0.5) * (0.6 + 0.4 * Math.sin(ix * 0.1 + iz * 0.2 + t));
          ctx.fillStyle = `rgba(${rgb},${a.toFixed(3)})`;
          ctx.beginPath(); ctx.arc(x, y, 0.5 + z * 1.5, 0, 6.283); ctx.fill();
        }
      }
    };
    const loop = () => { t += 0.012; draw(); raf = requestAnimationFrame(loop); };
    resize(); window.addEventListener("resize", resize);
    if (reduce) draw(); else loop();
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", resize); };
  }, [reduce]);
  return <canvas ref={ref} aria-hidden className="absolute inset-x-0 bottom-0 h-[72%] w-full opacity-80"
                 style={{ maskImage: "linear-gradient(to top,#000 45%,transparent)", WebkitMaskImage: "linear-gradient(to top,#000 45%,transparent)" }} />;
}

/** Texto contorno gigante que deriva no fundo (estilo pôster). */
function GiantType({ text }) {
  const reduce = useReducedMotion();
  return (
    <div aria-hidden className="pointer-events-none absolute inset-x-0 top-[14%] overflow-hidden">
      <motion.div className="flex whitespace-nowrap" animate={reduce ? undefined : { x: ["0%", "-50%"] }} transition={{ duration: 70, repeat: Infinity, ease: "linear" }}
        style={{ fontFamily: DISPLAY, fontWeight: 700, fontSize: "24vw", lineHeight: 1, letterSpacing: "-0.05em", color: "transparent", WebkitTextStroke: "1.5px var(--edge)" }}>
        {[0, 1].map((i) => <span key={i} className="pr-[6vw]">{text}</span>)}
      </motion.div>
    </div>
  );
}

const SPHERES = [
  { x: "3%", y: "18%", s: 130 }, { x: "91%", y: "12%", s: 90 }, { x: "86%", y: "66%", s: 160 },
  { x: "34%", y: "91%", s: 70 }, { x: "58%", y: "2%", s: 56 }, { x: "1%", y: "72%", s: 104 },
];
const HOLOS = [
  { x: "74%", y: "9%", w: 84, h: 150, t: "spec.A / 0.82" }, { x: "2.5%", y: "47%", w: 64, h: 40, t: "tex.B" }, { x: "90%", y: "47%", w: 96, h: 30, t: "flux" },
];

function Atmosphere() {
  const reduce = useReducedMotion();
  return (
    <div aria-hidden className="absolute inset-0 -z-10 overflow-hidden">
      <GiantType text="NEURAL SHELL ∞ LIVING SYSTEM ∞" />
      <Smoke count={8} intensity={0.9} seed={3} />
      <DotTerrain />
      {SPHERES.map((b, i) => (
        <motion.span key={i} className="absolute rounded-full" style={{
          left: b.x, top: b.y, width: b.s, height: b.s, opacity: 0.6, border: "1px solid var(--edge)", backdropFilter: "blur(3px)",
          background: "radial-gradient(circle at 30% 24%,var(--spec),transparent 38%),radial-gradient(circle at 72% 82%,var(--rim),transparent 58%)",
          boxShadow: "inset 0 0 30px -6px var(--rim),0 0 44px -18px var(--rim)" }}
          animate={reduce ? undefined : { y: [0, -26, 0], x: [0, 12, 0] }} transition={{ duration: 9 + i * 2, repeat: Infinity, ease: "easeInOut" }} />
      ))}
      {HOLOS.map((c, i) => (
        <motion.div key={i} className="absolute hidden lg:block" style={{ left: c.x, top: c.y }} animate={reduce ? undefined : { y: [0, -10, 0] }} transition={{ duration: 8 + i * 3, repeat: Infinity, ease: "easeInOut" }}>
          <div style={{ width: c.w, height: c.h, opacity: 0.32, borderRadius: 6, backgroundImage: "linear-gradient(135deg,#7ff0e0,#d29bff 35%,#ff8fc0 65%,#ffe27a)", mixBlendMode: "screen" }} />
          <div className="mt-1 text-[8px] tracking-[0.2em]" style={{ ...MONO, color: "var(--muted)" }}>{c.t}</div>
        </motion.div>
      ))}
    </div>
  );
}

/* ── 6. Primitivos: Bolha, Orbe ────────────────────────────────── */
const Bubble = React.forwardRef(function Bubble({ className = "", inner = "", style, tag, smoke = 0, morph = "a", delay = 0, children, ...rest }, ref) {
  return (
    <motion.div ref={ref} {...rest} className={`relative overflow-hidden aios-morph-${morph} ${className}`}
      style={{ background: "var(--glass)", backdropFilter: "blur(26px) saturate(160%)", WebkitBackdropFilter: "blur(26px) saturate(160%)",
               boxShadow: "inset 0 1px 0 var(--spec),inset 0 -34px 60px -44px var(--rim),0 30px 70px -30px var(--shadow)", animationDelay: `${-delay}s`, ...style }}>
      {smoke > 0 && <Smoke count={smoke} intensity={0.5} seed={delay + 2} soft />}
      <span aria-hidden className="pointer-events-none absolute inset-0" style={{ borderRadius: "inherit", background: "radial-gradient(120% 70% at 18% 0%,var(--spec),transparent 46%)", opacity: 0.45 }} />
      <span aria-hidden className="pointer-events-none absolute inset-0" style={{ borderRadius: "inherit", backgroundImage: GRAIN, opacity: 0.05, mixBlendMode: "overlay" }} />
      <span aria-hidden className="aios-iris pointer-events-none absolute inset-0"
            style={{ borderRadius: "inherit", padding: 1.5, opacity: 0.7, backgroundImage: "conic-gradient(from 200deg,var(--rim),transparent 22%,var(--violet) 48%,transparent 68%,var(--rim))",
                     WebkitMask: "linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0)", WebkitMaskComposite: "xor",
                     mask: "linear-gradient(#000 0 0) content-box exclude,linear-gradient(#000 0 0)" }} />
      {tag && (
        <span aria-hidden className="pointer-events-none absolute right-9 top-3.5 z-10 flex items-center gap-1.5 text-[8px] tracking-[0.16em]" style={{ ...MONO, color: "var(--muted)" }}>
          {tag}<span className="h-px w-5" style={{ background: "linear-gradient(90deg,var(--muted),var(--cyan))" }} />
          <span className="aios-breathe h-1.5 w-1.5 rounded-full" style={{ background: "var(--cyan)", boxShadow: "0 0 8px var(--glow)" }} />
        </span>
      )}
      <div className={`relative z-10 h-full min-h-0 ${inner}`}>{children}</div>
    </motion.div>
  );
});

/** Orbe/bloco de vidro (ícone). `square` = bloco arredondado estilo tile. */
function Orb({ icon, active, size = 52, square = false }) {
  const reduce = useReducedMotion();
  const ring = "radial-gradient(farthest-side,transparent calc(100% - 2px),#000 calc(100% - 1.5px))";
  const rad = square ? "1.15rem" : "9999px";
  return (
    <span className="relative grid shrink-0 place-items-center"
      style={{ width: size, height: size, borderRadius: rad, background: "radial-gradient(circle at 36% 24%,var(--spec),var(--cell) 58%)", border: "1px solid var(--edge)",
               boxShadow: "inset 0 1px 0 var(--spec),inset 0 -9px 16px -8px var(--glow),0 8px 16px -8px var(--shadow)", color: active ? "var(--cyan)" : "var(--muted)" }}>
      {active && (
        <>
          <span aria-hidden className="absolute inset-0" style={{ borderRadius: rad, boxShadow: "0 0 26px 2px var(--glow),inset 0 0 18px var(--glow)", background: "radial-gradient(circle at 50% 35%,var(--glow),transparent 70%)" }} />
          {square ? (
            <span aria-hidden className="aios-iris pointer-events-none absolute inset-0"
              style={{ borderRadius: rad, padding: 1.5, backgroundImage: "conic-gradient(from 200deg,var(--cyan),var(--violet),var(--warm),var(--rose),var(--cyan))",
                       WebkitMask: "linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0)", WebkitMaskComposite: "xor", mask: "linear-gradient(#000 0 0) content-box exclude,linear-gradient(#000 0 0)" }} />
          ) : (
            <motion.span aria-hidden className="pointer-events-none absolute -inset-[3px] rounded-full"
              style={{ background: "conic-gradient(var(--cyan),var(--violet),var(--warm),var(--rose),var(--cyan))", WebkitMask: ring, mask: ring }}
              animate={reduce ? undefined : { rotate: 360, scale: [1, 1.05, 1] }} transition={{ rotate: { duration: 12, repeat: Infinity, ease: "linear" }, scale: { duration: 3.2, repeat: Infinity } }} />
          )}
        </>
      )}
      <Icon name={icon} className="relative h-6 w-6" style={{ filter: active ? "drop-shadow(0 0 6px var(--cyan))" : "none" }} />
    </span>
  );
}

/* ── 7. Cérebro vivo ───────────────────────────────────────────── */
const HEMI = "M196 40C150 26 84 48 60 108C42 156 54 220 98 258C132 288 172 290 196 276Z";
const BRAIN = (() => {
  const r = rng(11);
  const nodes = [];
  [-1, 1].forEach((sx) => {
    let n = 0; let g = 0;
    while (n < 34 && g < 4000) {
      g++;
      const x = r() * 2 - 1; const y = r() * 2 - 1;
      if (x * x + y * y > 1) continue;
      nodes.push({ x: 200 + sx * 78 + x * 64, y: 165 + y * 100, side: sx, k: r() }); n++;
    }
  });
  const edges = []; const seen = new Set();
  nodes.forEach((a, i) => {
    nodes.map((b, j) => ({ j, d: (a.x - b.x) ** 2 + (a.y - b.y) ** 2 }))
      .filter((o) => o.j !== i && nodes[o.j].side === a.side).sort((p, q) => p.d - q.d).slice(0, 2)
      .forEach((o) => { const key = i < o.j ? `${i}-${o.j}` : `${o.j}-${i}`; if (!seen.has(key)) { seen.add(key); edges.push([i, o.j]); } });
  });
  const L = nodes.map((_, i) => i).filter((i) => nodes[i].side < 0 && nodes[i].x > 150);
  const R = nodes.map((_, i) => i).filter((i) => nodes[i].side > 0 && nodes[i].x < 250);
  L.slice(0, 7).forEach((i, k) => { if (R.length) edges.push([i, R[k % R.length]]); });
  const gyri = [-1, 1].flatMap((sx, si) => Array.from({ length: 10 }, (_, i) => {
    const y0 = 52 + i * 25; const pts = [];
    for (let k = 0; k <= 10; k++) pts.push([200 + sx * (6 + k * 14.5), y0 + Math.sin(k * 1.1 + i * 0.8 + si) * 7 + (r() - 0.5) * 6]);
    return smooth(pts);
  }));
  const pulses = edges.filter((_, i) => i % 4 === 0).slice(0, 18);
  return { nodes, edges, gyri, pulses };
})();

function BrainCore({ activity = 0.3, className = "" }) {
  const reduce = useReducedMotion();
  const sp = 1 + activity * 2.5;
  return (
    <svg viewBox="0 0 400 320" className={className} fill="none" style={{ filter: "drop-shadow(0 0 14px var(--glow))" }} aria-label="Cérebro do Kernel" role="img">
      <defs>
        <linearGradient id="brainIris" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" style={{ stopColor: "var(--cyan)" }} /><stop offset=".5" style={{ stopColor: "var(--violet)" }} /><stop offset="1" style={{ stopColor: "var(--warm)" }} />
        </linearGradient>
        <radialGradient id="brainFill" cx=".5" cy=".4" r=".7">
          <stop offset="0" style={{ stopColor: "var(--violet)" }} stopOpacity=".28" /><stop offset="1" style={{ stopColor: "var(--cyan)" }} stopOpacity=".04" />
        </radialGradient>
        <clipPath id="brainClip"><path d={HEMI} /><path d={HEMI} transform="translate(400 0) scale(-1 1)" /></clipPath>
      </defs>
      <motion.g style={{ originX: 0.5, originY: 0.5 }} animate={reduce ? undefined : { scale: [1, 1.025, 1] }} transition={{ duration: 5 / sp, repeat: Infinity, ease: "easeInOut" }}>
        <path d={HEMI} fill="url(#brainFill)" stroke="url(#brainIris)" strokeWidth="1.6" />
        <path d={HEMI} transform="translate(400 0) scale(-1 1)" fill="url(#brainFill)" stroke="url(#brainIris)" strokeWidth="1.6" />
        <g clipPath="url(#brainClip)">
          {BRAIN.gyri.map((d, i) => (
            <motion.path key={i} d={d} stroke="url(#brainIris)" strokeWidth="1" strokeLinecap="round" initial={{ pathLength: 1, opacity: 0.3 }}
              animate={reduce ? undefined : { pathLength: [0.35, 1, 0.35], opacity: [0.2, 0.5, 0.2] }} transition={{ duration: (6 + (i % 5)) / sp, repeat: Infinity, delay: i * 0.25, ease: "easeInOut" }} />
          ))}
          {BRAIN.edges.map(([a, b], i) => (
            <line key={i} x1={BRAIN.nodes[a].x} y1={BRAIN.nodes[a].y} x2={BRAIN.nodes[b].x} y2={BRAIN.nodes[b].y} stroke="var(--violet)" strokeWidth=".7" opacity=".32" />
          ))}
          {BRAIN.nodes.map((n, i) => (
            <motion.circle key={i} cx={n.x} cy={n.y} r="2.4" fill="var(--cyan)" animate={reduce ? undefined : { r: [2, 3.6, 2], opacity: [0.5, 1, 0.5] }}
              transition={{ duration: 3 / sp, repeat: Infinity, delay: n.k * 3 }} />
          ))}
          {BRAIN.pulses.map(([a, b], i) => (
            <motion.circle key={i} r="2.6" fill="var(--warm)" initial={{ cx: BRAIN.nodes[a].x, cy: BRAIN.nodes[a].y, opacity: 0 }}
              animate={reduce ? undefined : { cx: [BRAIN.nodes[a].x, BRAIN.nodes[b].x], cy: [BRAIN.nodes[a].y, BRAIN.nodes[b].y], opacity: [0, 1, 0] }}
              transition={{ duration: 2.2 / sp, repeat: Infinity, delay: (i % 6) * 0.4, ease: "easeInOut" }} />
          ))}
        </g>
      </motion.g>
    </svg>
  );
}

/* ── 8. BLOCOS (Tiles) — foco no hover, tilt 3D, luz que segue o mouse ─ */
const FocusCtx = createContext({ hot: null, setHot: () => {} });
const SPAN = { sm: "", wide: "col-span-2", tall: "row-span-2", lg: "col-span-2 row-span-2" };
const VARIANT = {
  glass: { bg: "var(--glass)", fg: "var(--text)", blur: true },
  iris: { bg: IRIS_FILL, fg: "#10101a", blur: false },
  ink: { bg: "var(--text)", fg: "var(--bg-a)", blur: false },
};

function Tile({ id, span = "sm", variant = "glass", index = 0, onClick, children, smoke = 0, label }) {
  const { hot, setHot } = useContext(FocusCtx);
  const reduce = useReducedMotion();
  const v = VARIANT[variant];
  const isHot = hot === id;
  const dim = hot !== null && !isHot;
  const mx = useMotionValue(0.5); const my = useMotionValue(0.5);
  const rx = useSpring(useTransform(my, [0, 1], [9, -9]), { stiffness: 140, damping: 20 });
  const ry = useSpring(useTransform(mx, [0, 1], [-11, 11]), { stiffness: 140, damping: 20 });
  const lx = useTransform(mx, [0, 1], ["0%", "100%"]);
  const ly = useTransform(my, [0, 1], ["0%", "100%"]);
  const light = useMotionTemplate`radial-gradient(340px circle at ${lx} ${ly}, rgba(255,255,255,.30), transparent 62%)`;

  const move = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    mx.set((e.clientX - r.left) / r.width); my.set((e.clientY - r.top) / r.height);
  };
  const leave = () => { mx.set(0.5); my.set(0.5); setHot(null); };

  return (
    <motion.div className={`relative ${SPAN[span]}`} style={{ zIndex: isHot ? 30 : 1 }}
      animate={reduce ? undefined : { y: [0, -5, 0] }} transition={{ duration: 6 + (index % 4), repeat: Infinity, ease: "easeInOut", delay: (index % 5) * 0.4 }}>
      <motion.div role="button" tabIndex={0} aria-label={label} onClick={onClick}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick?.(); } }}
        onPointerEnter={() => setHot(id)} onPointerMove={move} onPointerLeave={leave} onFocus={() => setHot(id)} onBlur={() => setHot(null)}
        className={`group relative h-full w-full cursor-pointer overflow-hidden rounded-[1.7rem] text-left outline-none transition-shadow duration-500 focus-visible:ring-2 focus-visible:ring-[var(--cyan)] ${variant === "iris" ? "aios-iris" : ""}`}
        style={{ rotateX: rx, rotateY: ry, transformPerspective: 900, background: v.bg, color: v.fg, border: "1px solid var(--edge)",
                 backdropFilter: v.blur ? "blur(24px) saturate(160%)" : undefined, WebkitBackdropFilter: v.blur ? "blur(24px) saturate(160%)" : undefined,
                 boxShadow: isHot ? "inset 0 1px 0 var(--spec),0 34px 60px -20px var(--shadow),0 0 56px -8px var(--glow)" : "inset 0 1px 0 var(--spec),0 16px 36px -22px var(--shadow)" }}
        animate={{ scale: isHot ? 1.06 : dim ? 0.965 : 1, opacity: dim ? 0.5 : 1, filter: dim ? "blur(2.5px) saturate(.6)" : "blur(0px) saturate(1)" }}
        transition={SPRING} whileTap={{ scale: 0.97 }}>
        {smoke > 0 && <Smoke count={smoke} intensity={0.45} seed={index + 3} soft />}
        <motion.span aria-hidden className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100" style={{ background: light }} />
        <span aria-hidden className="pointer-events-none absolute inset-0" style={{ backgroundImage: GRAIN, opacity: 0.05, mixBlendMode: "overlay" }} />
        <div className="relative z-10 flex h-full flex-col justify-between gap-2 p-4 sm:p-5">{children}</div>
      </motion.div>
    </motion.div>
  );
}

function TileHead({ tag, icon }) {
  return (
    <div className="flex items-start justify-between gap-2">
      <span className="truncate text-[9px] tracking-[0.2em] opacity-60" style={MONO}>{tag}</span>
      <motion.span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl" style={{ background: "rgba(128,128,140,.14)", border: "1px solid rgba(128,128,140,.32)" }}
        whileHover={{ rotate: 10, scale: 1.12 }} transition={JELLY}>
        <Icon name={icon} className="h-6 w-6" />
      </motion.span>
    </div>
  );
}

function TileFoot({ title, sub, big = false }) {
  return (
    <div className="min-w-0">
      <div className={`truncate leading-[0.95] tracking-[-0.04em] transition-[letter-spacing,font-weight] duration-500 group-hover:tracking-[0.02em] ${big ? "font-light group-hover:font-semibold" : "font-medium group-hover:font-bold"}`}
           style={{ fontFamily: DISPLAY, fontSize: big ? "clamp(34px,3.8vw,58px)" : "clamp(20px,2vw,28px)" }}>{title}</div>
      {sub && <div className="mt-1.5 truncate text-[11px] opacity-60" style={MONO}>{sub}</div>}
    </div>
  );
}

function Wave({ active }) {
  const reduce = useReducedMotion();
  return (
    <span className="flex h-10 shrink-0 items-end gap-[3px]" aria-hidden>
      {Array.from({ length: 14 }, (_, i) => (
        <motion.i key={i} className="w-[4px] rounded-full" style={{ background: "currentColor" }}
          animate={reduce ? { height: 10 } : { height: active ? [6, 38, 12, 30, 6] : [6, 10, 6] }}
          transition={{ duration: active ? 1.1 : 3.2, repeat: Infinity, delay: i * 0.08, ease: "easeInOut" }} />
      ))}
    </span>
  );
}

const SKILL_SPANS = ["wide", "sm", "sm", "wide", "sm", "sm"];
const SKILL_VARIANTS = ["glass", "iris", "glass", "ink", "glass", "iris"];

function SkillTile({ s, i, onOpen }) {
  const span = SKILL_SPANS[i % 6];
  return (
    <Tile id={`skill-${s.id}`} index={i + 4} span={span} variant={SKILL_VARIANTS[i % 6]} onClick={onOpen} label={`Abrir ${s.name}`}>
      <TileHead tag={`skill ${String(i + 1).padStart(2, "0")}`} icon={s.icon || "plug"} />
      <TileFoot title={s.name} sub={s.description} big={span === "wide"} />
    </Tile>
  );
}

function FolderTile({ folder, i, onOpen }) {
  const reduce = useReducedMotion();
  return (
    <Tile id={`folder-${folder.name}`} index={i + 6} span="lg" variant="ink" onClick={onOpen} label={`Abrir pasta ${folder.name}`}>
      <TileHead tag={`pasta · ${folder.items.length}`} icon="folder" />
      <div className="grid flex-1 grid-cols-2 place-content-center gap-2">
        {folder.items.slice(0, 4).map((s, k) => (
          <motion.span key={s.id} className="grid aspect-[2/1] place-items-center rounded-2xl" style={{ background: "rgba(128,128,140,.16)", border: "1px solid rgba(128,128,140,.3)" }}
            animate={reduce ? undefined : { y: [0, -3, 0] }} transition={{ duration: 3 + k, repeat: Infinity, delay: k * 0.3, ease: "easeInOut" }}>
            <Icon name={s.icon || "plug"} className="h-6 w-6" />
          </motion.span>
        ))}
      </div>
      <TileFoot title={folder.name} sub={folder.items.map((s) => s.name).join(" · ")} big />
    </Tile>
  );
}

const GRID = "grid auto-rows-[128px] grid-flow-dense grid-cols-2 gap-3 md:grid-cols-4 xl:auto-rows-[148px] xl:grid-cols-6";

function SectionTitle({ children, count }) {
  return (
    <div className="mb-3 mt-9 flex items-end gap-3">
      <Kinetic text={children} size="clamp(26px,3vw,40px)" weight={400} />
      {count != null && <span className="pb-1 text-[10px] tracking-[0.2em]" style={{ ...MONO, color: "var(--cyan)" }}>{count}</span>}
      <span className="mb-2 h-px flex-1" style={{ background: "linear-gradient(90deg,var(--edge),transparent)" }} />
    </div>
  );
}

/* ── 9. Home (tela de blocos) ──────────────────────────────────── */
function Omnibar({ messages, pending, onSend, voice }) {
  const [text, setText] = useState("");
  const [toast, setToast] = useState(null);
  const last = messages[messages.length - 1];
  const seen = useRef(last?.id);
  useEffect(() => {
    if (!last || last.id === seen.current || last.role !== "ai") return undefined;
    seen.current = last.id; setToast(last);
    const t = setTimeout(() => setToast(null), 7000);
    return () => clearTimeout(t);
  }, [last]);
  const submit = (e) => { e.preventDefault(); const v = text.trim(); if (!v) return; onSend(v); setText(""); };
  return (
    <div className="relative shrink-0 pt-3">
      <AnimatePresence>
        {(toast || pending) && (
          <motion.div key={pending ? "p" : toast?.id} initial={{ opacity: 0, y: 16, scale: 0.92 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10, scale: 0.95 }} transition={JELLY}
            className="absolute bottom-full left-6 mb-2 max-w-[70%] rounded-[1.6rem] rounded-bl-md px-5 py-3 text-sm"
            style={{ background: "var(--cell)", border: "1px solid var(--edge)", backdropFilter: "blur(20px)", boxShadow: "0 18px 40px -18px var(--shadow),0 0 30px -10px var(--glow)" }}>
            {pending ? <span className="flex gap-1.5">{[0, 1, 2].map((i) => <motion.i key={i} className="h-2 w-2 rounded-full" style={{ background: "var(--cyan)" }} animate={{ scale: [1, 1.6, 1] }} transition={{ duration: 1, repeat: Infinity, delay: i * 0.15 }} />)}</span> : toast.text}
          </motion.div>
        )}
      </AnimatePresence>
      <form onSubmit={submit} className="flex items-center gap-2 rounded-full py-2 pl-6 pr-2" style={{ background: "var(--glass)", border: "1px solid var(--edge)", backdropFilter: "blur(26px) saturate(160%)", boxShadow: "inset 0 1px 0 var(--spec),0 24px 50px -24px var(--shadow)" }}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Peça algo ao AI OS… ou use /comando" className="flex-1 bg-transparent text-sm outline-none placeholder:opacity-60" style={{ color: "var(--text)" }} />
        <motion.button type="button" aria-label="Comando por voz" onClick={voice.onToggle} whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.88 }} transition={JELLY}
          className="grid h-11 w-11 place-items-center rounded-full" style={{ color: voice.active ? "var(--cyan)" : "var(--muted)", background: "var(--chip)", boxShadow: voice.active ? "0 0 22px var(--glow)" : "none" }}>
          <Icon name="mic" className="h-5 w-5" />
        </motion.button>
        <motion.button type="submit" aria-label="Enviar" whileHover={{ scale: 1.1 }} whileTap={{ scaleX: 0.86, scaleY: 0.8 }} transition={JELLY}
          className="grid h-11 w-11 place-items-center rounded-full text-[#10101a]" style={{ background: IRIS, boxShadow: text ? "0 0 22px var(--glow)" : "none" }}>
          <Icon name="send" className="h-5 w-5" />
        </motion.button>
      </form>
    </div>
  );
}

function Home({ groups, messages, logs, theme, onToggleTheme, voice, onNavigate, consoleOpen, onToggleConsole, activity, openFolder, setOpenFolder, onSend, pending, bridge }) {
  const [hot, setHot] = useState(null);
  const d = useClock();
  const last3 = messages.slice(-3);
  const logLines = logs.slice(-5).map((l) => `[${String(l.level).toLowerCase()}] ${l.msg}`);
  const folder = groups.folders.find((f) => f.name === openFolder) || null;
  const empty = !groups.loose.length && !groups.folders.length;

  return (
    <FocusCtx.Provider value={{ hot, setHot }}>
      <div className="flex h-full min-h-0 flex-col">
        <div className="no-scrollbar min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-2 pb-4 pt-1" onPointerLeave={() => setHot(null)}>
          <AnimatePresence mode="wait" initial={false}>
            {!folder ? (
              <motion.div key="start" initial={{ opacity: 0, y: 24, filter: "blur(10px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }} exit={{ opacity: 0, y: -24, filter: "blur(10px)" }} transition={SPRING}>
                {/* HERO */}
                <div className="flex flex-wrap items-end justify-between gap-6 pt-3">
                  <div>
                    <div className="mb-1 text-[11px] tracking-[0.3em]" style={{ ...MONO, color: "var(--cyan)" }}>{greet(d.getHours()).toUpperCase()} · v7 · <Readout base={72.4} drift={4} digits={2} /></div>
                    <Kinetic text="AI OS" weight={200} />
                    <LiveLine lines={["o que vamos fazer hoje?", "toque num bloco para abrir uma habilidade", "ou fale / digite na barra abaixo", "tudo aqui se move — passe o mouse para focar"]} className="mt-2 text-sm" style={{ ...MONO, color: "var(--muted)" }} />
                  </div>
                  <div className="text-right">
                    <div className="tabular-nums" style={{ fontFamily: DISPLAY, fontWeight: 200, fontSize: "clamp(34px,4vw,60px)", letterSpacing: "-0.04em", lineHeight: 1 }}>{d.toLocaleTimeString("pt-BR", { hour12: false })}</div>
                    <div className="mt-1 text-[10px] tracking-[0.2em]" style={{ ...MONO, color: "var(--muted)" }}>{d.toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long" }).toUpperCase()} · {bridge === "pywebview" ? "KERNEL LINKED" : "MOCK"}</div>
                  </div>
                </div>

                {/* SISTEMA */}
                <SectionTitle count="04">Sistema</SectionTitle>
                <div className={GRID} style={{ perspective: 1400 }}>
                  <Tile id="chat" span="lg" variant="glass" index={0} smoke={3} onClick={() => onNavigate("chat")} label="Abrir chat">
                    <TileHead tag="comms // live" icon="chat" />
                    <div className="flex flex-col gap-2 overflow-hidden">
                      {last3.map((m) => (
                        <motion.div key={m.id} initial={{ opacity: 0, x: m.role === "user" ? 16 : -16 }} animate={{ opacity: 1, x: 0 }} transition={SPRING}
                          className={`line-clamp-2 max-w-[90%] rounded-2xl px-3 py-1.5 text-xs ${m.role === "user" ? "self-end" : "self-start"}`}
                          style={{ background: m.role === "user" ? "var(--bubble-user)" : "var(--chip)", border: "1px solid var(--edge)" }}>{m.text}</motion.div>
                      ))}
                    </div>
                    <TileFoot title="Conversa" sub="toque para abrir em tela cheia" big />
                  </Tile>

                  <Tile id="brain" span="lg" variant="glass" index={1} smoke={2} onClick={() => onNavigate("brain")} label="Abrir cérebro">
                    <TileHead tag="cortex" icon="brain" />
                    <div className="pointer-events-none absolute inset-x-6 top-8 bottom-16 grid place-items-center"><BrainCore activity={activity} className="max-h-full w-full" /></div>
                    <div className="relative mt-auto"><TileFoot title="Cérebro" sub={`atividade ${(activity * 100).toFixed(0)}% · sinapses ${BRAIN.nodes.length}`} big /></div>
                  </Tile>

                  <Tile id="voice" span="wide" variant="iris" index={2} onClick={voice.onToggle} label="Alternar comando por voz">
                    <TileHead tag={voice.active ? "mic // on" : "mic // off"} icon="mic" />
                    <div className="flex items-end justify-between gap-3">
                      <TileFoot title="Voz" sub={voice.active ? "SISTEMA ATIVO // OUVINDO" : "toque para ativar"} big />
                      <Wave active={voice.active} />
                    </div>
                  </Tile>

                  <Tile id="theme" span="sm" variant="ink" index={3} onClick={onToggleTheme} label="Alternar tema">
                    <TileHead tag="display" icon={theme === "dark" ? "moon" : "sun"} />
                    <TileFoot title="Tema" sub={theme === "dark" ? "escuro" : "claro"} />
                  </Tile>

                  <Tile id="kernel" span="sm" variant="glass" index={4} onClick={onToggleConsole} label="Alternar logs do kernel">
                    <TileHead tag={consoleOpen ? "log // visível" : "log // oculto"} icon="terminal" />
                    <div className="min-w-0">
                      <LiveLine lines={logLines.length ? logLines : ["sem sinais"]} className="text-[11px]" style={{ ...MONO, color: "var(--cyan)" }} />
                      <div className="mt-1 text-[11px] opacity-60" style={MONO}>{logs.length} sinais</div>
                    </div>
                  </Tile>
                </div>

                {/* HABILIDADES */}
                <SectionTitle count={String(groups.loose.length + groups.folders.length).padStart(2, "0")}>Habilidades</SectionTitle>
                <div className={GRID} style={{ perspective: 1400 }}>
                  {groups.folders.map((f, i) => <FolderTile key={f.name} folder={f} i={i} onOpen={() => setOpenFolder(f.name)} />)}
                  {groups.loose.map((s, i) => <SkillTile key={s.id} s={s} i={i} onOpen={() => onNavigate(s.id)} />)}
                  {empty && (
                    <Tile id="empty" span="wide" variant="glass" index={9} label="Nenhuma habilidade">
                      <TileHead tag="vazio" icon="plug" />
                      <TileFoot title="Sem habilidades" sub="o Kernel ainda não carregou plugins" />
                    </Tile>
                  )}
                </div>
              </motion.div>
            ) : (
              <motion.div key={`folder-${folder.name}`} initial={{ opacity: 0, x: 60, filter: "blur(10px)" }} animate={{ opacity: 1, x: 0, filter: "blur(0px)" }} exit={{ opacity: 0, x: 60, filter: "blur(10px)" }} transition={SPRING}>
                <div className="flex items-center gap-5 pt-3">
                  <motion.button type="button" onClick={() => setOpenFolder(null)} aria-label="Voltar" whileHover={{ x: -5, scale: 1.08 }} whileTap={{ scale: 0.9 }} transition={JELLY}
                    className="grid h-14 w-14 place-items-center rounded-full outline-none focus-visible:ring-2 focus-visible:ring-[var(--cyan)]" style={{ background: "var(--glass)", border: "1px solid var(--edge)", backdropFilter: "blur(20px)" }}>
                    <Icon name="back" className="h-6 w-6" />
                  </motion.button>
                  <div>
                    <div className="text-[10px] tracking-[0.3em]" style={{ ...MONO, color: "var(--cyan)" }}>PASTA · {folder.items.length} ITENS</div>
                    <Kinetic text={folder.name} />
                  </div>
                </div>
                <div className={`${GRID} mt-8`} style={{ perspective: 1400 }}>
                  {folder.items.map((s, i) => <SkillTile key={s.id} s={s} i={i + 1} onOpen={() => onNavigate(s.id)} />)}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
        <Omnibar messages={messages} pending={pending} onSend={onSend} voice={voice} />
      </div>
    </FocusCtx.Provider>
  );
}

/* ── 10. Menu expansível (blocos + pastas) ─────────────────────── */
function MenuItem({ icon, label, hint, active, expanded, onClick, indent = false, trailing, layoutId = "menu-active" }) {
  return (
    <motion.button type="button" onClick={onClick} aria-label={label} aria-current={active ? "page" : undefined} title={expanded ? undefined : label}
      whileHover={{ x: 4, scale: 1.03 }} whileTap={{ scale: 0.95 }} transition={JELLY}
      className={`relative flex w-full items-center gap-3 rounded-[1.3rem] p-1.5 pr-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-[var(--cyan)] ${indent ? "pl-5" : ""}`}>
      {active && <motion.span layoutId={layoutId} transition={SPRING} className="absolute inset-0 rounded-[1.3rem]" style={{ background: "var(--chip)", boxShadow: "inset 0 0 24px -8px var(--glow),0 0 0 1px var(--edge)" }} />}
      <span className="relative"><Orb icon={icon} square active={active} size={indent ? 38 : 46} /></span>
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.span key="l" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -10 }} transition={{ duration: 0.2 }} className="relative min-w-0 flex-1">
            <span className="block truncate text-sm" style={{ color: active ? "var(--text)" : "var(--muted)" }}>{label}</span>
            {hint && <span className="block truncate text-[10px]" style={{ ...MONO, color: "var(--muted)" }}>{hint}</span>}
          </motion.span>
        )}
      </AnimatePresence>
      {expanded && trailing && <span className="relative">{trailing}</span>}
    </motion.button>
  );
}

function SectionLabel({ expanded, children }) {
  return expanded
    ? <div className="px-3 pb-1 pt-3 text-[9px] tracking-[0.26em]" style={{ ...MONO, color: "var(--muted)" }}>{children}</div>
    : <div className="mx-auto my-2 h-px w-8" style={{ background: "var(--edge)" }} />;
}

function VoiceControl({ active, busy, onToggle, expanded }) {
  const reduce = useReducedMotion();
  return (
    <motion.button type="button" role="switch" aria-checked={active} aria-label="Comando por voz" disabled={busy} onClick={onToggle}
      whileHover={{ scale: 1.03 }} whileTap={{ scaleX: 0.95, scaleY: 0.92 }} transition={JELLY}
      className="relative flex w-full items-center gap-3 rounded-[1.3rem] p-1.5 pr-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-[var(--cyan)] disabled:opacity-60"
      style={{ background: active ? "var(--chip)" : "transparent", boxShadow: active ? "inset 0 0 24px -8px var(--glow)" : "none" }}>
      <span className="relative grid h-[46px] w-[46px] shrink-0 place-items-center rounded-[1.15rem]"
        style={{ background: "radial-gradient(circle at 36% 24%,var(--spec),var(--cell) 58%)", border: "1px solid var(--edge)",
                 boxShadow: active ? "inset 0 1px 0 var(--spec),inset 0 -10px 18px var(--glow),0 8px 16px -6px var(--shadow)" : "inset 0 1px 0 var(--spec),0 8px 16px -6px var(--shadow)" }}>
        <AnimatePresence>
          {active && (
            <>
              <motion.span key="halo" aria-hidden initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1.3 }} exit={{ opacity: 0, scale: 0.6 }} transition={SPRING}
                className="absolute -inset-3 rounded-full" style={{ background: "radial-gradient(circle,var(--glow),transparent 68%)", filter: "blur(7px)" }} />
              {!reduce && [0, 0.9].map((dl) => (
                <motion.span key={dl} aria-hidden className="absolute inset-0 rounded-[1.15rem]" style={{ border: "1.5px solid var(--cyan)" }}
                  animate={{ scale: [1, 1.7], opacity: [0.6, 0] }} transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut", delay: dl }} />
              ))}
            </>
          )}
        </AnimatePresence>
        <Icon name="mic" className="relative h-6 w-6" style={{ color: active ? "var(--text)" : "var(--muted)", filter: active ? "drop-shadow(0 0 6px var(--cyan))" : "none" }} />
      </span>
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.span key="t" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -10 }} transition={{ duration: 0.2 }} className="flex min-w-0 flex-1 items-center gap-3">
            <span className="min-w-0 flex-1 leading-tight">
              <span className="block text-[9px] tracking-[0.2em]" style={{ ...MONO, color: "var(--muted)" }}>COMANDO POR VOZ</span>
              <span className="block truncate text-[10px] font-bold tracking-wider" style={{ ...MONO, color: active ? "var(--cyan)" : "var(--muted)" }}>{active ? "SISTEMA ATIVO // OUVINDO" : "STANDBY // OFF"}</span>
            </span>
            <span className="relative h-6 w-11 shrink-0 rounded-full" style={{ background: active ? "linear-gradient(90deg,var(--cyan),var(--violet))" : "var(--chip)", boxShadow: "inset 0 2px 5px var(--shadow)", border: "1px solid var(--edge)" }}>
              <motion.span className="absolute top-[2px] h-5 w-5 rounded-full" animate={{ left: active ? 22 : 2 }} transition={{ type: "spring", stiffness: 500, damping: 22 }}
                style={{ background: "radial-gradient(circle at 30% 25%,#fff,#dfe4ee 60%,#aab1c4)", boxShadow: "0 3px 8px rgba(0,0,0,.4)" }} />
            </span>
          </motion.span>
        )}
      </AnimatePresence>
    </motion.button>
  );
}

function Menu({ expanded, onToggle, view, onNavigate, skills, groups, voice, consoleOpen, onToggleConsole, openFolder, setOpenFolder }) {
  const [q, setQ] = useState("");
  const [openF, setOpenF] = useState({});
  const query = q.trim().toLowerCase();
  const match = (s) => `${s.name} ${s.description || ""}`.toLowerCase().includes(query);
  const loose = groups.loose.filter(match);
  const folders = groups.folders.map((f) => ({ ...f, items: f.items.filter(match) })).filter((f) => f.items.length);
  const nothing = !loose.length && !folders.length;

  return (
    <Bubble morph="b" delay={4} initial={{ x: -60, opacity: 0 }} animate={{ x: 0, opacity: 1, width: expanded ? 300 : 96 }} transition={SPRING} className="h-full shrink-0" inner="flex flex-col px-3 py-4">
      <div className="flex items-center gap-3">
        <motion.button type="button" onClick={onToggle} aria-label={expanded ? "Recolher menu" : "Expandir menu"} aria-expanded={expanded} whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.9 }} transition={JELLY}
          className="rounded-[1.15rem] outline-none focus-visible:ring-2 focus-visible:ring-[var(--cyan)]">
          <Orb icon="menu" square size={46} active={expanded} />
        </motion.button>
        <AnimatePresence initial={false}>
          {expanded && (
            <motion.div key="brand" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex-1 leading-tight">
              <div className="text-xl font-light tracking-[0.2em]" style={{ fontFamily: DISPLAY }}>ai os</div>
              <div className="text-[9px] tracking-[0.3em]" style={{ ...MONO, color: "var(--cyan)" }}>v7 · tecla M</div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <AnimatePresence initial={false}>
        {expanded && skills.length > 5 && (
          <motion.label key="s" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 40 }} exit={{ opacity: 0, height: 0 }} className="mt-3 flex items-center gap-2 overflow-hidden rounded-full px-4" style={{ background: "var(--chip)", border: "1px solid var(--edge)" }}>
            <Icon name="search" className="h-4 w-4 shrink-0" style={{ color: "var(--muted)" }} />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="buscar habilidade…" className="w-full bg-transparent text-xs outline-none" style={{ color: "var(--text)" }} />
          </motion.label>
        )}
      </AnimatePresence>

      <nav className="no-scrollbar mt-2 flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto overflow-x-hidden">
        <SectionLabel expanded={expanded}>NÚCLEO</SectionLabel>
        <MenuItem icon="home" label="Início" hint="blocos e pastas" active={view === "home" && !openFolder} expanded={expanded} onClick={() => { setOpenFolder(null); onNavigate("home"); }} />
        <MenuItem icon="chat" label="Chat unificado" hint="conversa em tela cheia" active={view === "chat"} expanded={expanded} onClick={() => onNavigate("chat")} />
        <MenuItem icon="brain" label="Cérebro" hint="visão do kernel" active={view === "brain"} expanded={expanded} onClick={() => onNavigate("brain")} />

        <SectionLabel expanded={expanded}>HABILIDADES</SectionLabel>
        {folders.map((f) => {
          const isOpen = !!openF[f.name] || !!query;
          const hasActive = f.items.some((s) => s.id === view);
          return (
            <div key={f.name}>
              <MenuItem icon="folder" label={f.name} hint={`${f.items.length} itens`} active={hasActive && !isOpen} expanded={expanded} layoutId="menu-active-folder"
                onClick={() => { if (!expanded) { onToggle(); setOpenF((o) => ({ ...o, [f.name]: true })); } else setOpenF((o) => ({ ...o, [f.name]: !o[f.name] })); }}
                trailing={<motion.span animate={{ rotate: isOpen ? 0 : -90 }} transition={SPRING} className="block"><Icon name="chevron" className="h-4 w-4" style={{ color: "var(--muted)" }} /></motion.span>} />
              <AnimatePresence initial={false}>
                {expanded && isOpen && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={SPRING} className="overflow-hidden">
                    {f.items.map((s) => <MenuItem key={s.id} indent icon={s.icon || "plug"} label={s.name} hint={s.description} active={view === s.id} expanded={expanded} onClick={() => onNavigate(s.id)} />)}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
        <AnimatePresence initial={false}>
          {loose.map((s) => (
            <motion.div key={s.id} initial={{ opacity: 0, scale: 0.5 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.5 }} transition={SPRING}>
              <MenuItem icon={s.icon || "plug"} label={s.name} hint={s.description} active={view === s.id} expanded={expanded} onClick={() => onNavigate(s.id)} />
            </motion.div>
          ))}
        </AnimatePresence>
        {expanded && nothing && <div className="px-3 py-2 text-xs" style={{ color: "var(--muted)" }}>Nenhuma habilidade encontrada.</div>}

        <SectionLabel expanded={expanded}>SISTEMA</SectionLabel>
        <MenuItem icon="terminal" label="Logs do Kernel" hint={consoleOpen ? "visível" : "oculto"} active={consoleOpen} expanded={expanded} onClick={onToggleConsole} layoutId="menu-active-console" />
      </nav>

      <div className="mt-2 border-t pt-3" style={{ borderColor: "var(--edge)" }}><VoiceControl {...voice} expanded={expanded} /></div>
    </Bubble>
  );
}

/* ── 11. Header, Tema, Chat ────────────────────────────────────── */
function ThemeToggle({ theme, onToggle }) {
  const light = theme === "light";
  return (
    <button type="button" role="switch" aria-checked={light} aria-label="Alternar modo claro/escuro" onClick={onToggle}
      className="relative flex h-10 w-[84px] items-center rounded-full p-1 outline-none focus-visible:ring-2 focus-visible:ring-[var(--cyan)]"
      style={{ background: "var(--chip)", border: "1px solid var(--edge)", boxShadow: "inset 0 2px 6px var(--shadow)" }}>
      <Icon name="moon" className="absolute left-3 h-4 w-4" style={{ color: "var(--muted)" }} />
      <Icon name="sun" className="absolute right-3 h-4 w-4" style={{ color: "var(--muted)" }} />
      <motion.span className="relative z-10 grid h-8 w-8 place-items-center rounded-full text-[#10101a]" animate={{ x: light ? 44 : 0, rotate: light ? 360 : 0 }} transition={JELLY}
        style={{ background: "linear-gradient(145deg,var(--cyan),var(--violet),var(--warm))", boxShadow: "0 0 18px 1px var(--glow),inset 0 1px 0 rgba(255,255,255,.6)" }}>
        <Icon name={light ? "sun" : "moon"} className="h-4 w-4" />
      </motion.span>
    </button>
  );
}

function Header({ theme, onToggleTheme, bridge, title, trail, voiceOn, fullscreen, onToggleFullscreen, widgetMode, onToggleWidget }) {
  const reduce = useReducedMotion();
  return (
    <Bubble morph="a" delay={9} initial={{ y: -30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={SPRING} className="!rounded-full" style={{ animation: "none" }} inner="flex items-center justify-between gap-4 py-2.5 pl-6 pr-3">
      <div className="flex min-w-0 items-center gap-3">
        <motion.span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: bridge === "pywebview" ? "var(--cyan)" : "var(--violet)" }} animate={reduce ? undefined : { scale: [1, 1.3, 1] }} transition={{ duration: 1.8, repeat: Infinity }} />
        <span className="hidden text-[10px] tracking-[0.2em] sm:inline" style={{ ...MONO, color: "var(--muted)" }}>{trail}</span>
        <AnimatePresence mode="wait" initial={false}>
          <motion.span key={title} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={SPRING} className="truncate text-sm font-medium tracking-wide">{title}</motion.span>
        </AnimatePresence>
        <span className="hidden rounded-full px-2 py-0.5 text-[10px] tracking-[0.12em] md:inline" style={{ ...MONO, background: "var(--chip)", color: "var(--cyan)", border: "1px solid var(--edge)" }}>
          {bridge === "pywebview" ? "core_1 // linked" : "core_1 // mock"}
        </span>
      </div>

      <div className="flex min-w-0 flex-1 items-center justify-center">
        <AnimatePresence mode="wait" initial={false}>
          {voiceOn ? (
            <motion.div key="voice" initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.8 }} transition={SPRING}
              className="flex items-center gap-3 rounded-full px-5 py-1.5" style={{ border: "1px solid var(--cyan)", background: "var(--chip)", boxShadow: "0 0 30px -4px var(--glow),inset 0 0 18px -8px var(--glow)" }}>
              <span className="flex h-4 items-end gap-[3px]">
                {[0, 1, 2, 3, 4].map((i) => <motion.i key={i} className="w-[3px] rounded-full" style={{ background: "var(--cyan)" }} animate={reduce ? { height: 8 } : { height: [3, 15, 6, 16, 3] }} transition={{ duration: 1.1, repeat: Infinity, delay: i * 0.12 }} />)}
              </span>
              <span className="text-[11px] font-bold tracking-[0.16em]" style={{ ...MONO, color: "var(--cyan)" }}>SISTEMA ATIVO // OUVINDO</span>
            </motion.div>
          ) : (
            <motion.svg key="ecg" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} viewBox="0 0 120 24" className="hidden h-6 w-32 md:block" fill="none" aria-hidden>
              <path d="M0 12H30L36 12L40 3L46 21L50 12H72L76 8L80 12H120" stroke="var(--edge)" strokeWidth="1.2" />
              <motion.path d="M0 12H30L36 12L40 3L46 21L50 12H72L76 8L80 12H120" stroke="var(--rose)" strokeWidth="1.6" strokeLinecap="round" strokeDasharray="22 120" animate={reduce ? undefined : { strokeDashoffset: [0, -142] }} transition={{ duration: 2.4, repeat: Infinity, ease: "linear" }} />
            </motion.svg>
          )}
        </AnimatePresence>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <motion.button type="button" aria-label={widgetMode ? "Sair do modo widget" : "Modo widget"} onClick={onToggleWidget}
          whileHover={{ scale: 1.12 }} whileTap={{ scale: 0.88 }} transition={JELLY}
          className="grid h-10 w-10 place-items-center rounded-full outline-none focus-visible:ring-2 focus-visible:ring-[var(--cyan)]"
          style={{ background: widgetMode ? "var(--chip)" : "transparent", border: "1px solid var(--edge)", color: widgetMode ? "var(--cyan)" : "var(--muted)", boxShadow: widgetMode ? "0 0 18px -4px var(--glow)" : "none" }}>
          <Icon name="widget" className="h-5 w-5" style={widgetMode ? { filter: "drop-shadow(0 0 5px var(--cyan))" } : {}} />
        </motion.button>
        <motion.button type="button" aria-label={fullscreen ? "Sair da tela cheia" : "Tela cheia"} onClick={onToggleFullscreen}
          whileHover={{ scale: 1.12 }} whileTap={{ scale: 0.88 }} transition={JELLY}
          className="grid h-10 w-10 place-items-center rounded-full outline-none focus-visible:ring-2 focus-visible:ring-[var(--cyan)]"
          style={{ background: fullscreen ? "var(--chip)" : "transparent", border: "1px solid var(--edge)", color: fullscreen ? "var(--cyan)" : "var(--muted)", boxShadow: fullscreen ? "0 0 18px -4px var(--glow)" : "none" }}>
          <Icon name={fullscreen ? "minimize" : "maximize"} className="h-5 w-5" style={fullscreen ? { filter: "drop-shadow(0 0 5px var(--cyan))" } : {}} />
        </motion.button>
        <ThemeToggle theme={theme} onToggle={onToggleTheme} />
      </div>
    </Bubble>
  );
}

const SUGGESTIONS = ["/skills", "status do kernel", "o que você consegue fazer?"];

function ChatPanel({ messages, pending, onSend, effortMode, onEffortChange, effortInfo }) {
  const [text, setText] = useState("");
  const endRef = useRef(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages, pending]);
  const submit = (e) => { e.preventDefault(); const v = text.trim(); if (!v) return; onSend(v); setText(""); };
  return (
    <Bubble morph="a" delay={2} smoke={3} tag="comms" className="h-full" inner="flex flex-col p-5 pt-6">
      <div className="mb-3"><Kinetic text="Conversa" size="clamp(34px,4.2vw,64px)" weight={250} /></div>
      <div className="mb-3 text-xs" style={{ color: "var(--text)" }}>
        <label htmlFor="effort-mode">Profundidade: </label>
        <select id="effort-mode" value={effortMode} onChange={(e) => onEffortChange(e.target.value)} style={{ color: "var(--text)", background: "var(--cell)" }}>
          {['AUTO', 'FAST', 'BALANCED', 'DEEP'].map((mode) => <option key={mode} value={mode}>{mode}</option>)}
        </select>
        <span> · {pending ? 'Processando' : 'Aguardando'} · {effortInfo}</span>
      </div>
      <div className="no-scrollbar flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">
        <AnimatePresence initial={false}>
          {messages.map((m) => (
            <motion.div key={m.id} layout initial={{ opacity: 0, y: 16, scale: 0.92 }} animate={{ opacity: 1, y: 0, scale: 1 }} whileHover={{ scale: 1.025, y: -2 }} transition={JELLY}
              className={`max-w-[86%] px-5 py-3 text-sm leading-relaxed ${m.role === "user" ? "self-end rounded-[1.9rem] rounded-br-lg" : "self-start rounded-[1.9rem] rounded-bl-lg"}`}
              style={{ background: m.role === "user" ? "var(--bubble-user)" : "var(--chip)", backdropFilter: "blur(10px)", border: `1px solid ${m.role === "user" ? "var(--violet)" : "var(--edge)"}`, boxShadow: m.role === "user" ? "0 0 22px -8px var(--violet)" : "none" }}>
              {m.text}
            </motion.div>
          ))}
          {pending && (
            <motion.div key="typing" layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex gap-1.5 self-start rounded-[1.9rem] px-5 py-3.5" style={{ background: "var(--chip)", border: "1px solid var(--edge)" }}>
              {[0, 1, 2].map((i) => <motion.span key={i} className="h-2 w-2 rounded-full" style={{ background: "var(--cyan)" }} animate={{ scale: [1, 1.6, 1], opacity: [0.5, 1, 0.5] }} transition={{ duration: 1, repeat: Infinity, delay: i * 0.15 }} />)}
            </motion.div>
          )}
        </AnimatePresence>
        <div ref={endRef} />
      </div>
      {messages.length <= 1 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <motion.button key={s} type="button" onClick={() => onSend(s)} whileHover={{ y: -2, scale: 1.05 }} whileTap={{ scale: 0.94 }} transition={JELLY}
              className="rounded-full px-4 py-1.5 text-xs" style={{ ...MONO, background: "var(--chip)", border: "1px solid var(--edge)", color: "var(--cyan)" }}>{s}</motion.button>
          ))}
        </div>
      )}
      <form onSubmit={submit} className="mt-3 flex items-center gap-2 rounded-full py-1.5 pl-5 pr-1.5" style={{ background: "var(--chip)", border: "1px solid var(--edge)", backdropFilter: "blur(10px)" }}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Digite uma mensagem ou /comando…" className="flex-1 bg-transparent text-sm outline-none placeholder:opacity-60" style={{ color: "var(--text)" }} />
        <motion.button type="submit" aria-label="Enviar" whileHover={{ scale: 1.08 }} whileTap={{ scaleX: 0.86, scaleY: 0.8 }} transition={JELLY}
          className="grid h-10 w-10 place-items-center rounded-full" style={{ color: "var(--violet)", background: "var(--chip)", boxShadow: text ? "0 0 18px var(--glow)" : "none" }}>
          <Icon name="send" className="h-5 w-5" />
        </motion.button>
      </form>
    </Bubble>
  );
}

/* ── 12. Palco: cérebro + Sub-GUIs ─────────────────────────────── */
function BrainStage({ skills, onNavigate, activity }) {
  const reduce = useReducedMotion();
  return (
    <Bubble morph="b" delay={6} smoke={5} tag="cortex" className="h-full" inner="relative">
      <div className="absolute inset-0 grid place-items-center p-10 sm:p-14"><BrainCore activity={activity} className="max-h-full w-full max-w-[560px]" /></div>
      <div className="absolute left-7 top-5">
        <Kinetic text="Cérebro" size="clamp(34px,4.2vw,64px)" weight={250} />
        <div className="mt-1 text-[10px] tracking-[0.14em]" style={{ ...MONO, color: "var(--muted)" }}>{skills.length ? "clique numa bolha para abrir a habilidade" : "aguardando habilidades…"}</div>
      </div>
      {skills.map((s, i) => {
        const a = (i / Math.max(skills.length, 1)) * Math.PI * 2 - Math.PI / 2;
        return (
          <div key={s.id} className="absolute -translate-x-1/2 -translate-y-1/2" style={{ left: `${50 + 40 * Math.cos(a)}%`, top: `${54 + 36 * Math.sin(a)}%` }}>
            <motion.button type="button" onClick={() => onNavigate(s.id)} aria-label={s.name} whileHover={{ scale: 1.18 }} whileTap={{ scaleX: 0.9, scaleY: 0.86 }}
              animate={reduce ? undefined : { y: [0, -9, 0] }} transition={{ y: { duration: 5 + i, repeat: Infinity, ease: "easeInOut" }, default: JELLY }} className="flex flex-col items-center gap-1 outline-none">
              <Orb icon={s.icon || "plug"} size={64} active />
              <span className="rounded-full px-2.5 py-0.5 text-[10px] tracking-wider" style={{ ...MONO, background: "var(--chip)", border: "1px solid var(--edge)", backdropFilter: "blur(8px)" }}>{s.name}</span>
            </motion.button>
          </div>
        );
      })}
      <div className="absolute bottom-5 left-7 text-[9px] tracking-[0.2em]" style={{ ...MONO, color: "var(--muted)" }}>
        atividade <Readout base={activity * 100} drift={8} digits={1} className="text-[var(--text)]" /> % · sinapses {BRAIN.nodes.length}
      </div>
    </Bubble>
  );
}

/* ── 11b. Sub-GUI de Automações — rotinas executáveis com logs visuais ── */
const AUTOMATIONS = [
  { id: "sync-memory", name: "Sincronizar Memória", desc: "Consolida contexto e indexa vetores.", steps: ["Lendo memória de longo prazo…", "Indexando 1.248 vetores…", "Consolidando contexto…", "Memória sincronizada."] },
  { id: "scan-system", name: "Diagnóstico do Sistema", desc: "Verifica núcleos, sinapses e latência.", steps: ["Probando Core1…", "Probando Core2…", "Medindo latência de sinapses…", "Sistema saudável · 0 anomalias."] },
  { id: "tidy-files", name: "Organizar Arquivos", desc: "Categoriza e Compacta arquivos locais.", steps: ["Mapeando diretórios…", "Categorizando 342 arquivos…", "Compactando redundâncias…", "Arquivos organizados."] },
  { id: "digest-news", name: "Resumo de Notícias", desc: "Agrega fontes e gera briefing.", steps: ["Coletando 18 fontes…", "Filtrando relevância…", "Redigindo briefing…", "Briefing pronto."] },
  { id: "backup-state", name: "Backup de Estado", desc: "Snapshot completo do Kernel.", steps: ["Congelando estado…", "Serializando 4.7 MB…", "Gravando snapshot…", "Backup concluído."] },
  { id: "purge-cache", name: "Limpar Cache", desc: "Remove caches expirados e órfãos.", steps: ["Localizando caches…", "Removendo 212 entradas…", "Liberando 128 MB…", "Cache limpo."] },
];

function AutomationsSubGUI({ skill, kernel, pushLog }) {
  const [running, setRunning] = useState(null);
  const [stepIdx, setStepIdx] = useState(-1);
  const [localLogs, setLocalLogs] = useState([]);
  const [history, setHistory] = useState([]);
  const logRef = useRef(null);

  const addLocal = useCallback((entry) => {
    setLocalLogs((prev) => [...prev.slice(-80), { id: uid(), ...entry }]);
  }, []);

  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" }); }, [localLogs]);

  const runRoutine = useCallback(async (routine) => {
    if (running) return;
    setRunning(routine.id);
    setStepIdx(0);
    addLocal({ level: "INFO", core: "Auto", msg: `[${routine.id}] Iniciando: ${routine.name}` });
    pushLog({ level: "INFO", core: "Automation", msg: `Rotina iniciada: ${routine.name}` });

    for (let i = 0; i < routine.steps.length; i++) {
      setStepIdx(i);
      await wait(650 + Math.random() * 500);
      addLocal({ level: i === routine.steps.length - 1 ? "INFO" : "DEBUG", core: "Auto", msg: `  ${routine.steps[i]}` });
      pushLog({ level: "DEBUG", core: "Automation", msg: `${routine.id} passo ${i + 1}/${routine.steps.length}: ${routine.steps[i]}` });
    }

    const res = await kernel.call("run_skill", skill.id, "run", { routine: routine.id });
    const ok = res?.ok !== false;
    addLocal({ level: ok ? "INFO" : "ERROR", core: "Auto", msg: ok ? `[${routine.id}] Concluído com sucesso.` : `[${routine.id}] Falhou: ${res?.error || "erro desconhecido"}` });
    pushLog({ level: ok ? "INFO" : "ERROR", core: "Automation", msg: ok ? `Rotina concluída: ${routine.name}` : `Rotina falhou: ${routine.name}` });
    setHistory((prev) => [{ id: uid(), name: routine.name, time: new Date(), ok }, ...prev.slice(0, 9)]);
    setRunning(null);
    setStepIdx(-1);
  }, [running, skill.id, kernel, pushLog, addLocal]);

  const clearLogs = () => { setLocalLogs([]); addLocal({ level: "INFO", core: "Auto", msg: "Logs locais limpos." }); };

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="mb-2 text-[10px] tracking-[0.3em]" style={{ ...MONO, color: "var(--cyan)" }}>HABILIDADE · AUTOMAÇÕES</div>
          <Kinetic text="Automações" />
          <p className="mt-2 max-w-md text-sm" style={{ color: "var(--muted)" }}>{skill.description || "Execute rotinas do Kernel e acompanhe os logs em tempo real."}</p>
        </div>
        <div className="hidden shrink-0 text-right sm:block">
          <div className="text-[10px] tracking-[0.2em]" style={{ ...MONO, color: "var(--muted)" }}>ROTINAS</div>
          <div className="text-3xl font-light" style={{ fontFamily: DISPLAY }}>{AUTOMATIONS.length}</div>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
        {/* Lista de rotinas */}
        <div className="no-scrollbar overflow-y-auto pr-1">
          <div className="mb-2 text-[9px] tracking-[0.26em]" style={{ ...MONO, color: "var(--muted)" }}>ROTINAS DISPONÍVEIS</div>
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
            {AUTOMATIONS.map((r, i) => {
              const isThis = running === r.id;
              const isOther = running && !isThis;
              const prog = isThis ? (stepIdx + 1) / r.steps.length : 0;
              return (
                <motion.div key={r.id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ ...SPRING, delay: i * 0.06 }}
                  className="relative overflow-hidden rounded-[1.4rem] p-4" style={{ background: "var(--chip)", border: `1px solid ${isThis ? "var(--cyan)" : "var(--edge)"}`, boxShadow: isThis ? "0 0 28px -6px var(--glow),inset 0 0 18px -10px var(--glow)" : "none" }}>
                  <div className="mb-2 flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium" style={{ color: "var(--text)" }}>{r.name}</div>
                      <div className="mt-0.5 truncate text-[11px]" style={{ ...MONO, color: "var(--muted)" }}>{r.desc}</div>
                    </div>
                    <motion.span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl" whileHover={{ rotate: 10, scale: 1.12 }} transition={JELLY}
                      style={{ background: "rgba(128,128,140,.14)", border: "1px solid rgba(128,128,140,.3)", color: isThis ? "var(--cyan)" : "var(--muted)" }}>
                      <Icon name="bolt" className="h-5 w-5" style={isThis ? { filter: "drop-shadow(0 0 6px var(--cyan))" } : {}} />
                    </motion.span>
                  </div>

                  {isThis && (
                    <div className="mb-2.5 mt-2">
                      <div className="mb-1 flex items-center justify-between text-[9px] tracking-wider" style={{ ...MONO, color: "var(--muted)" }}>
                        <span>passo {stepIdx + 1}/{r.steps.length}</span><span>{Math.round(prog * 100)}%</span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full" style={{ background: "var(--edge)" }}>
                        <motion.div className="h-full rounded-full" style={{ background: "linear-gradient(90deg,var(--cyan),var(--violet))" }} animate={{ width: `${prog * 100}%` }} transition={{ duration: 0.4 }} />
                      </div>
                      <div className="mt-1.5 truncate text-[10px]" style={{ ...MONO, color: "var(--cyan)" }}>{r.steps[stepIdx]}</div>
                    </div>
                  )}

                  <motion.button type="button" disabled={!!isOther} onClick={() => runRoutine(r)}
                    whileHover={!isOther ? { scale: 1.03 } : {}} whileTap={!isOther ? { scaleX: 0.95, scaleY: 0.9 } : {}} transition={JELLY}
                    className="mt-1 w-full rounded-full px-4 py-2 text-xs font-medium disabled:opacity-50" style={{
                      background: isThis ? "var(--chip)" : IRIS, color: isThis ? "var(--cyan)" : "#10101a",
                      border: isThis ? "1px solid var(--cyan)" : "none", boxShadow: isThis ? "none" : "0 0 18px -6px var(--glow)" }}>
                    {isThis ? "executando…" : isOther ? "ocupado" : "Executar"}
                  </motion.button>
                </motion.div>
              );
            })}
          </div>
        </div>

        {/* Painel de logs locais */}
        <div className="flex min-h-0 flex-col rounded-[1.4rem] p-4" style={{ background: "var(--chip)", border: "1px solid var(--edge)" }}>
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-2 text-[9px] tracking-[0.2em]" style={{ ...MONO, color: "var(--cyan)" }}>
              <Icon name="terminal" className="h-4 w-4" /> LOGS DA ROTINA
            </div>
            <button type="button" onClick={clearLogs} className="text-[9px] tracking-wider transition-colors hover:text-[var(--text)]" style={{ ...MONO, color: "var(--muted)" }}>limpar</button>
          </div>
          <div ref={logRef} className="no-scrollbar min-h-0 flex-1 overflow-y-auto text-[11px] leading-5" style={MONO}>
            {localLogs.length === 0 ? (
              <div className="flex h-full items-center justify-center text-center" style={{ color: "var(--muted)" }}>
                <span>Nenhuma rotina executada ainda.<br />Toque em "Executar" para começar.</span>
              </div>
            ) : (
              <div className="space-y-0.5">
                {localLogs.map((l) => {
                  const c = LEVEL_COLOR[l.level] || "var(--violet)";
                  return (
                    <motion.div key={l.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={SPRING} className="break-words" style={{ color: l.level === "ERROR" ? "var(--err)" : "var(--text)" }}>
                      <span style={{ color: c }}>{String(l.level).toLowerCase()}</span> <span style={{ color: "var(--muted)" }}>{l.core} ·</span> {l.msg}
                    </motion.div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Histórico recente */}
      {history.length > 0 && (
        <div className="shrink-0">
          <div className="mb-1.5 text-[9px] tracking-[0.26em]" style={{ ...MONO, color: "var(--muted)" }}>EXECUÇÕES RECENTES</div>
          <div className="flex flex-wrap gap-2">
            {history.map((h) => (
              <motion.span key={h.id} initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} transition={JELLY}
                className="flex items-center gap-2 rounded-full px-3 py-1.5 text-[10px]" style={{ ...MONO, background: "var(--chip)", border: `1px solid ${h.ok ? "var(--edge)" : "var(--err)"}`, color: "var(--muted)" }}>
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: h.ok ? "var(--cyan)" : "var(--err)", boxShadow: `0 0 6px ${h.ok ? "var(--cyan)" : "var(--err)"}` }} />
                {h.name} · {h.time.toLocaleTimeString("pt-BR", { hour12: false })}
              </motion.span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Registry Plug-and-View: id da habilidade do Kernel -> componente da Sub-GUI.
 * Exemplo:  const SUBGUI_REGISTRY = { minhaskill: MinhaSkillSubGUI };
 * Cada componente recebe { skill, kernel, pushLog }. Sem registro, cai na GenericSubGUI.
 */
const SUBGUI_REGISTRY = { automations: AutomationsSubGUI };

function GenericSubGUI({ skill, kernel, pushLog }) {
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    const res = await kernel.call("run_skill", skill.id, "open", {});
    pushLog({ level: res?.ok === false ? "ERROR" : "INFO", core: "Core1", msg: res?.log || res?.error || `${skill.id}.open concluído` });
    setBusy(false);
  };
  return (
    <div className="flex h-full flex-col justify-between gap-4">
      <div>
        <div className="mb-2 text-[10px] tracking-[0.3em]" style={{ ...MONO, color: "var(--cyan)" }}>HABILIDADE{skill.folder ? ` · ${skill.folder.toUpperCase()}` : ""}</div>
        <Kinetic text={skill.name} />
        <p className="mt-3 max-w-md text-sm" style={{ color: "var(--muted)" }}>{skill.description || "Esta habilidade ainda não registrou uma Sub-GUI visual. Acione-a pelo chat ou pelo botão abaixo."}</p>
      </div>
      <div className="grid flex-1 place-items-center"><motion.div animate={{ rotate: [0, 6, -6, 0] }} transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }}><Orb icon={skill.icon || "plug"} size={96} active /></motion.div></div>
      <div className="flex flex-wrap gap-2">
        <motion.button type="button" disabled={busy} onClick={run} whileHover={{ scale: 1.06 }} whileTap={{ scaleX: 0.92, scaleY: 0.88 }} transition={JELLY}
          className="rounded-full px-6 py-2.5 text-sm font-medium text-[#10101a] disabled:opacity-60" style={{ background: IRIS, boxShadow: "0 0 24px -4px var(--glow)" }}>{busy ? "executando…" : "Executar habilidade"}</motion.button>
      </div>
    </div>
  );
}

function SubGUIFrame({ skill, kernel, pushLog }) {
  const Comp = SUBGUI_REGISTRY[skill.id] || GenericSubGUI;
  return (
    <Bubble morph="b" delay={5} smoke={3} tag="viewport" className="h-full" inner="p-6 pt-7">
      <Comp skill={skill} kernel={kernel} pushLog={pushLog} />
    </Bubble>
  );
}

/* ── 12b. Widget Popup — Dynamic Island flutuante, arrastável ─── */
const WIDGET_SIZE = 70;
const WIDGET_EXPAND_W = 360;
const WIDGET_EXPAND_H = 200;

function WidgetPopup({ kernel, theme, voice, onSend, pending, messages, pushLog }) {
  const reduce = useReducedMotion();
  const [pos, setPos] = useState(() => {
    const w = typeof window !== "undefined" ? window.innerWidth : 1280;
 const h = typeof window !== "undefined" ? window.innerHeight : 720;
    return { x: w - WIDGET_SIZE - 24, y: h - WIDGET_SIZE - 24 };
  });
  const [hovered, setHovered] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [text, setText] = useState("");
  const [pinned, setPinned] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [showNotifs, setShowNotifs] = useState(false);
  const dragStart = useRef(null);
  const posStart = useRef(null);
  const hasDragged = useRef(false);
  const lastNotifId = useRef(null);

  const expanded = hovered || pinned || dragging;

  const addNotification = useCallback((notif) => {
    setNotifications((prev) => [{ id: uid(), time: new Date(), ...notif }, ...prev.slice(0, 12)]);
  }, []);

  useEffect(() => {
    const onLog = (e) => {
      const l = e.detail;
      if (l && (l.level === "ERROR" || l.level === "WARN" || l.level === "WARNING")) {
        addNotification({ level: l.level, title: l.core || "Kernel", body: l.msg });
      }
    };
    const onMsg = (e) => {
      const m = e.detail;
      if (m && m.role === "ai") addNotification({ level: "INFO", title: "Kernel", body: m.text });
    };
    window.addEventListener("aios:log", onLog);
    window.addEventListener("aios:message", onMsg);
    return () => {
      window.removeEventListener("aios:log", onLog);
      window.removeEventListener("aios:message", onMsg);
    };
  }, [addNotification]);

  useEffect(() => {
    const last = messages[messages.length - 1];
    if (!last || last.role !== "ai" || last.id === lastNotifId.current) return;
    lastNotifId.current = last.id;
    addNotification({ level: "INFO", title: "Kernel", body: last.text });
  }, [messages, addNotification]);

  useEffect(() => {
    if (dragging) return undefined;
    const w = window.innerWidth; const h = window.innerHeight;
    setPos((p) => ({
      x: Math.min(Math.max(8, p.x), w - WIDGET_SIZE - 8),
      y: Math.min(Math.max(8, p.y), h - WIDGET_SIZE - 8),
    }));
  }, [dragging]);

  useEffect(() => {
    if (!dragging) return undefined;
    const move = (e) => {
      if (!dragStart.current) return;
      const dx = e.clientX - dragStart.current.x;
      const dy = e.clientY - dragStart.current.y;
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) hasDragged.current = true;
      const nx = posStart.current.x + dx;
      const ny = posStart.current.y + dy;
      const w = window.innerWidth; const hh = window.innerHeight;
      const ex = expanded ? WIDGET_EXPAND_W : WIDGET_SIZE;
      const ey = expanded ? WIDGET_EXPAND_H : WIDGET_SIZE;
      setPos({
        x: Math.min(Math.max(4, nx), w - ex - 4),
        y: Math.min(Math.max(4, ny), hh - ey - 4),
      });
    };
    const up = () => { setDragging(false); dragStart.current = null; };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
  }, [dragging, expanded]);

  useEffect(() => {
    if (dragging) kernel.call("set_window_position", pos.x, pos.y);
  }, [pos, dragging, kernel]);

  const startDrag = (e) => {
    if (expanded) return;
    hasDragged.current = false;
    dragStart.current = { x: e.clientX, y: e.clientY };
    posStart.current = { ...pos };
    setDragging(true);
  };

  const submit = (e) => {
    e.preventDefault();
    const v = text.trim();
    if (!v) return;
    onSend(v); setText("");
  };

  const w = expanded ? WIDGET_EXPAND_W : WIDGET_SIZE;
  const h = expanded ? WIDGET_EXPAND_H : WIDGET_SIZE;
  const unread = notifications.length;

  return (
    <motion.div
      className="fixed z-[9999]"
      style={{ left: pos.x, top: pos.y, width: w, height: h }}
      animate={{ width: w, height: h }}
      transition={SPRING}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => { if (!pinned && !dragging) setHovered(false); setShowNotifs(false); }}
    >
      <motion.div
        className="relative h-full w-full overflow-hidden"
        style={{
          borderRadius: expanded ? "1.8rem" : "9999px",
          background: expanded ? "var(--glass)" : "var(--cell)",
          backdropFilter: "blur(28px) saturate(180%)",
          WebkitBackdropFilter: "blur(28px) saturate(180%)",
          border: "1px solid var(--edge)",
          boxShadow: expanded
            ? "inset 0 1px 0 var(--spec),0 28px 60px -20px var(--shadow),0 0 50px -10px var(--glow)"
            : "inset 0 1px 0 var(--spec),inset 0 -12px 22px -10px var(--glow),0 12px 30px -10px var(--shadow),0 0 28px -6px var(--glow)",
          cursor: expanded ? "default" : dragging ? "grabbing" : "grab",
        }}
        animate={{ borderRadius: expanded ? "1.8rem" : "9999px" }}
        transition={SPRING}
        onPointerDown={startDrag}
      >
        <span aria-hidden className="pointer-events-none absolute inset-0" style={{
          borderRadius: "inherit",
          background: "radial-gradient(120% 70% at 18% 0%,var(--spec),transparent 46%)",
          opacity: 0.4,
        }} />
        <span aria-hidden className="aios-iris pointer-events-none absolute inset-0" style={{
          borderRadius: "inherit", padding: 1.5, opacity: 0.6,
          backgroundImage: "conic-gradient(from 200deg,var(--rim),transparent 22%,var(--violet) 48%,transparent 68%,var(--rim))",
          WebkitMask: "linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0)",
          WebkitMaskComposite: "xor",
          mask: "linear-gradient(#000 0 0) content-box exclude,linear-gradient(#000 0 0)",
        }} />

        <AnimatePresence mode="wait" initial={false}>
          {!expanded ? (
            <motion.div key="orb" className="relative flex h-full w-full items-center justify-center"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, scale: 0.6 }} transition={{ duration: 0.2 }}
            >
              <motion.span className="absolute inset-2 rounded-full" style={{
                background: "radial-gradient(circle at 36% 28%,var(--spec),transparent 60%)",
              }} animate={reduce ? undefined : { scale: [1, 1.08, 1] }} transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }} />
              <motion.span className="absolute inset-0 rounded-full" style={{
                border: "1.5px solid var(--cyan)",
              }} animate={reduce ? undefined : { scale: [1, 1.25], opacity: [0.5, 0] }} transition={{ duration: 2, repeat: Infinity, ease: "easeOut" }} />
              <Icon name="ai" className="relative h-8 w-8" style={{ color: "var(--cyan)", filter: "drop-shadow(0 0 8px var(--cyan))" }} />
              {unread > 0 && (
                <motion.span key={unread} initial={{ scale: 0 }} animate={{ scale: 1 }} transition={JELLY}
                  className="absolute -right-0.5 -top-0.5 grid h-5 min-w-5 place-items-center rounded-full px-1 text-[9px] font-bold"
                  style={{ background: "var(--rose)", color: "#fff", boxShadow: "0 0 10px var(--rose)" }}>
                  {unread > 9 ? "9+" : unread}
                </motion.span>
              )}
              {voice.active && (
                <motion.span className="absolute bottom-1 right-1 h-2 w-2 rounded-full" style={{ background: "var(--cyan)", boxShadow: "0 0 8px var(--cyan)" }}
                  animate={{ scale: [1, 1.4, 1] }} transition={{ duration: 1, repeat: Infinity }} />
              )}
            </motion.div>
          ) : (
            <motion.div key="panel" className="relative flex h-full w-full flex-col p-3"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}
              onPointerDown={(e) => e.stopPropagation()}
            >
              <div className="mb-2 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <motion.span className="grid h-7 w-7 place-items-center rounded-full" style={{ background: "var(--chip)", border: "1px solid var(--edge)" }}>
                    <Icon name="ai" className="h-4 w-4" style={{ color: "var(--cyan)" }} />
                  </motion.span>
                  <span className="text-[10px] tracking-[0.18em]" style={{ ...MONO, color: "var(--cyan)" }}>AI OS · WIDGET</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <motion.button type="button" aria-label={voice.active ? "Desligar microfone" : "Ligar microfone"} onClick={voice.onToggle}
                    whileHover={{ scale: 1.15 }} whileTap={{ scale: 0.85 }} transition={JELLY} disabled={voice.busy}
                    className="grid h-8 w-8 place-items-center rounded-full disabled:opacity-50"
                    style={{ background: voice.active ? "var(--chip)" : "transparent", border: "1px solid var(--edge)", color: voice.active ? "var(--cyan)" : "var(--muted)", boxShadow: voice.active ? "0 0 14px -3px var(--glow)" : "none" }}>
                    <Icon name="mic" className="h-4 w-4" style={voice.active ? { filter: "drop-shadow(0 0 4px var(--cyan))" } : {}} />
                  </motion.button>
                  <motion.button type="button" aria-label="Notificações" onClick={() => setShowNotifs((s) => !s)}
                    whileHover={{ scale: 1.15 }} whileTap={{ scale: 0.85 }} transition={JELLY}
                    className="relative grid h-8 w-8 place-items-center rounded-full"
                    style={{ background: showNotifs ? "var(--chip)" : "transparent", border: "1px solid var(--edge)", color: showNotifs ? "var(--cyan)" : "var(--muted)" }}>
                    <Icon name="bell" className="h-4 w-4" />
                    {unread > 0 && (
                      <span className="absolute -right-0.5 -top-0.5 grid h-3.5 min-w-3.5 place-items-center rounded-full px-0.5 text-[8px] font-bold" style={{ background: "var(--rose)", color: "#fff" }}>{unread > 9 ? "9+" : unread}</span>
                    )}
                  </motion.button>
                  <motion.button type="button" aria-label={pinned ? "Desafixar" : "Fixar"} onClick={() => setPinned((p) => !p)}
                    whileHover={{ scale: 1.15 }} whileTap={{ scale: 0.85 }} transition={JELLY}
                    className="grid h-8 w-8 place-items-center rounded-full"
                    style={{ background: pinned ? "var(--chip)" : "transparent", border: "1px solid var(--edge)", color: pinned ? "var(--cyan)" : "var(--muted)" }}>
                    <span className="text-[10px]" style={MONO}>{pinned ? "ON" : "·"}</span>
                  </motion.button>
                </div>
              </div>

              <AnimatePresence mode="wait" initial={false}>
                {showNotifs ? (
                  <motion.div key="notifs" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }} transition={SPRING}
                    className="no-scrollbar min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto">
                    {notifications.length === 0 ? (
                      <div className="flex h-full items-center justify-center text-center text-[10px]" style={{ ...MONO, color: "var(--muted)" }}>Sem notificações</div>
                    ) : notifications.map((n) => {
                      const c = LEVEL_COLOR[n.level] || "var(--violet)";
                      return (
                        <motion.div key={n.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={SPRING}
                          className="rounded-xl p-2 text-[10px] leading-snug" style={{ background: "var(--chip)", border: "1px solid var(--edge)" }}>
                          <div className="mb-0.5 flex items-center gap-1.5">
                            <span className="h-1.5 w-1.5 rounded-full" style={{ background: c, boxShadow: `0 0 6px ${c}` }} />
                            <span className="truncate font-bold tracking-wider" style={{ ...MONO, color: c }}>{n.title}</span>
                            <span className="ml-auto shrink-0 text-[8px]" style={{ ...MONO, color: "var(--muted)" }}>{n.time.toLocaleTimeString("pt-BR", { hour12: false })}</span>
                          </div>
                          <div className="truncate" style={{ color: "var(--text)" }}>{n.body}</div>
                        </motion.div>
                      );
                    })}
                  </motion.div>
                ) : (
                  <motion.div key="input" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} transition={SPRING}
                    className="flex min-h-0 flex-1 flex-col">
                    {voice.active && (
                      <div className="mb-1.5 flex items-center gap-2">
                        <span className="flex h-4 items-end gap-[3px]">
                          {[0, 1, 2, 3, 4].map((i) => (
                            <motion.i key={i} className="w-[3px] rounded-full" style={{ background: "var(--cyan)" }}
                              animate={reduce ? { height: 6 } : { height: [3, 12, 5, 14, 3] }} transition={{ duration: 1.1, repeat: Infinity, delay: i * 0.12 }} />
                          ))}
                        </span>
                        <span className="text-[9px] font-bold tracking-[0.14em]" style={{ ...MONO, color: "var(--cyan)" }}>OVINDO…</span>
                      </div>
                    )}
                    {pending && (
                      <div className="mb-1.5 flex gap-1">
                        {[0, 1, 2].map((i) => <motion.span key={i} className="h-1.5 w-1.5 rounded-full" style={{ background: "var(--cyan)" }} animate={{ scale: [1, 1.5, 1], opacity: [0.5, 1, 0.5] }} transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.15 }} />)}
                      </div>
                    )}
                    <form onSubmit={submit} className="mt-auto flex items-center gap-1.5 rounded-full py-1 pl-3 pr-1" style={{ background: "var(--chip)", border: "1px solid var(--edge)" }}>
                      <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Comando rápido…" autoFocus
                        className="flex-1 bg-transparent text-xs outline-none placeholder:opacity-60" style={{ color: "var(--text)" }} />
                      <motion.button type="submit" aria-label="Enviar" whileHover={{ scale: 1.15 }} whileTap={{ scale: 0.8 }} transition={JELLY}
                        className="grid h-8 w-8 place-items-center rounded-full text-[#10101a]" style={{ background: IRIS, boxShadow: text ? "0 0 14px var(--glow)" : "none" }}>
                        <Icon name="send" className="h-4 w-4" />
                      </motion.button>
                    </form>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </motion.div>
  );
}

/* ── 13. Console do Kernel ─────────────────────────────────────── */
const LEVEL_COLOR = { INFO: "var(--cyan)", WARN: "var(--warm)", WARNING: "var(--warm)", ERROR: "var(--err)", DEBUG: "var(--violet)" };

function KernelConsole({ logs, open, onToggle }) {
  const endRef = useRef(null);
  const reduce = useReducedMotion();
  useEffect(() => { if (open) endRef.current?.scrollIntoView({ block: "end" }); }, [logs, open]);
  const errs = logs.filter((l) => l.level === "ERROR").length;
  return (
    <Bubble morph="a" delay={11} animate={{ opacity: 1 }} className="!rounded-[2.2rem]" style={{ animation: "none" }} inner="px-7 py-3">
      <button type="button" onClick={onToggle} aria-expanded={open} className="flex w-full items-center gap-2 text-left text-[11px] tracking-[0.14em] outline-none" style={{ ...MONO, color: "var(--muted)" }}>
        <Icon name="terminal" className="h-4 w-4" style={{ color: "var(--cyan)" }} /><span style={{ color: "var(--text)" }}>kernel log</span><span>// synapses</span>
        <span className="ml-auto flex items-center gap-3">
          <span>{logs.length} sig</span><span style={{ color: errs ? "var(--err)" : "var(--muted)" }}>{errs} err</span>
          <motion.span animate={{ rotate: open ? 0 : -90 }} transition={SPRING}><Icon name="chevron" className="h-4 w-4" /></motion.span>
        </span>
      </button>
      <motion.div initial={false} animate={{ height: open ? 96 : 0, opacity: open ? 1 : 0, marginTop: open ? 8 : 0 }} transition={SPRING} className="no-scrollbar overflow-y-auto text-[12px] leading-6" style={MONO}>
        <div className="relative pl-5">
          <span aria-hidden className="absolute bottom-2 left-[5px] top-2 w-px" style={{ backgroundImage: "linear-gradient(var(--cyan),var(--violet),var(--warm))", opacity: 0.55 }} />
          {logs.map((l, i) => {
            const c = LEVEL_COLOR[l.level] || "var(--violet)"; const last = i === logs.length - 1;
            return (
              <motion.div key={l.id} initial={reduce ? false : { opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} whileHover={{ x: 4 }} transition={SPRING} className="relative" style={{ color: l.level === "ERROR" ? "var(--err)" : "var(--text)" }}>
                <motion.span aria-hidden className="absolute -left-[19px] top-[9px] h-[7px] w-[7px] rounded-full" style={{ background: c, boxShadow: `0 0 8px ${c}` }}
                  animate={{ scale: last && !reduce ? [1, 1.7, 1] : 1 }} transition={last ? { duration: 1.6, repeat: Infinity } : SPRING} />
                <span style={{ color: c }}>{String(l.level).toLowerCase()}</span> <span style={{ color: "var(--muted)" }}>{l.core} ·</span> {l.msg}
              </motion.div>
            );
          })}
        </div>
        <div ref={endRef} />
      </motion.div>
    </Bubble>
  );
}

/* ── 14. MASTER SHELL (estado + lógica) ────────────────────────── */
let _uid = 0;
const uid = () => ++_uid;
const readLS = (k, d) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } };
const VIEW_NAMES = { home: "Início", chat: "Conversa", brain: "Cérebro" };

const groupSkills = (skills) => {
  const loose = []; const map = new Map();
  skills.forEach((s) => {
    if (s.folder) { if (!map.has(s.folder)) map.set(s.folder, []); map.get(s.folder).push(s); } else loose.push(s);
  });
  return { loose, folders: [...map].map(([name, items]) => ({ name, items })) };
};

const PAGE = { initial: { opacity: 0, scale: 0.97, filter: "blur(12px)" }, animate: { opacity: 1, scale: 1, filter: "blur(0px)" }, exit: { opacity: 0, scale: 0.97, filter: "blur(12px)" }, transition: SPRING };

export default function MasterShell() {
  const kernel = useKernel();

  const [theme, setTheme] = useState(() => readLS("aios.theme", "dark"));
  useEffect(() => {
    try { localStorage.setItem("aios.theme", theme); } catch { /* noop */ }
    kernel.call("set_theme", theme);
  }, [theme]); // eslint-disable-line react-hooks/exhaustive-deps
  const toggleTheme = () => setTheme((t) => (t === "dark" ? "light" : "dark"));

  const [menuOpen, setMenuOpen] = useState(() => { const v = readLS("aios.menu", null); return v === null ? window.innerWidth >= 1200 : v === "1"; });
  useEffect(() => { try { localStorage.setItem("aios.menu", menuOpen ? "1" : "0"); } catch { /* noop */ } }, [menuOpen]);
  useEffect(() => {
    const onKey = (e) => {
      const t = e.target?.tagName;
      if (t === "INPUT" || t === "TEXTAREA" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key.toLowerCase() === "m") setMenuOpen((o) => !o);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const [view, setView] = useState("home");
  const [openFolder, setOpenFolder] = useState(null);
  const [skills, setSkills] = useState([]);
  const [logs, setLogs] = useState([]);
  const [consoleOpen, setConsoleOpen] = useState(true);
  const [messages, setMessages] = useState([{ id: uid(), role: "ai", text: "AI OS v7 pronto. Toque num bloco, fale ou digite um comando." }]);
  const [pending, setPending] = useState(false);
  const [effortMode, setEffortMode] = useState('AUTO');
  const [effortInfo, setEffortInfo] = useState('Limites conversacionais; modelo não confirmado');

  useEffect(() => {
    let active = true;
    kernel.call('get_effort_mode').then((result) => {
      if (active && result?.ok) setEffortMode(result.mode);
      else if (active) setEffortInfo('Configuração do Kernel indisponível');
    });
    return () => { active = false; };
  }, [kernel.call]);
  const changeEffort = useCallback(async (mode) => {
    const result = await kernel.call('set_effort_mode', mode);
    if (result?.ok) { setEffortMode(result.mode); setEffortInfo('Aplicado às próximas conversas'); }
    else setEffortInfo(result?.error || 'Falha ao salvar configuração');
  }, [kernel.call]);
  const [voiceOn, setVoiceOn] = useState(false);
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [widgetMode, setWidgetMode] = useState(false);

  const pushLog = useCallback((l) => setLogs((prev) => [...prev.slice(-199), { id: uid(), ...l }]), []);
  const pushMessage = useCallback((m) => setMessages((prev) => [...prev, { id: uid(), ...m }]), []);

  useEffect(() => {
    let alive = true;
    (async () => {
      const [sk, lg] = await Promise.all([kernel.call("list_skills"), kernel.call("get_logs")]);
      if (!alive) return;
      if (Array.isArray(sk)) setSkills(cleanSkills(sk));
      if (Array.isArray(lg)) setLogs(lg.map((l) => ({ id: uid(), ...l })));
    })();
    const onLog = (e) => pushLog(e.detail);
    const onMsg = (e) => pushMessage(e.detail);
    const onSkills = (e) => Array.isArray(e.detail) && setSkills(cleanSkills(e.detail));
    window.addEventListener("aios:log", onLog);
    window.addEventListener("aios:message", onMsg);
    window.addEventListener("aios:skills", onSkills);
    return () => {
      alive = false;
      window.removeEventListener("aios:log", onLog);
      window.removeEventListener("aios:message", onMsg);
      window.removeEventListener("aios:skills", onSkills);
    };
  }, [kernel.call, pushLog, pushMessage]); // eslint-disable-line react-hooks/exhaustive-deps

  const sendCommand = useCallback(async (text) => {
    pushMessage({ role: "user", text });
    setPending(true);
    const res = await kernel.call("send_command", text);
    setPending(false);
    if (res?.effort) setEffortInfo(`Efetivo: ${res.effort.effective} · ${res.effort.budget.num_predict} tokens · modelo não confirmado`);
    if (res?.error) {
      pushLog({ level: "ERROR", core: "Shell", msg: res.error });
      pushMessage({ role: "ai", text: "Falha ao falar com o Kernel. Veja o log." });
      return;
    }
    if (res?.reply) pushMessage({ role: "ai", text: res.reply });
    res?.logs?.forEach(pushLog);
  }, [kernel.call, pushLog, pushMessage]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleVoice = useCallback(async () => {
    const next = !voiceOn;
    setVoiceBusy(true);
    setVoiceOn(next);
    const res = await kernel.call("set_voice", next);
    if (res?.ok === false) {
      setVoiceOn(!next);
      pushLog({ level: "ERROR", core: "Voice", msg: res.error || "Falha ao alternar voz." });
    } else {
      pushLog({ level: "INFO", core: "Voice", msg: next ? "Escuta ativa." : "Escuta desativada." });
    }
    setVoiceBusy(false);
  }, [voiceOn, kernel.call, pushLog]); // eslint-disable-line react-hooks/exhaustive-deps

  /* divisor fluido entre Chat e Palco */
  const wrapRef = useRef(null);
  const [split, setSplit] = useState(40);
  const [drag, setDrag] = useState(false);
  useEffect(() => {
    if (!drag) return undefined;
    const move = (e) => {
      const r = wrapRef.current?.getBoundingClientRect();
      if (r) setSplit(Math.min(62, Math.max(28, ((e.clientX - r.left) / r.width) * 100)));
    };
    const up = () => setDrag(false);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
  }, [drag]);

  const groups = useMemo(() => groupSkills(skills), [skills]);
  const known = view === "home" || view === "chat" || view === "brain" || skills.some((s) => s.id === view);
  const v = known ? view : "home";
  const activeSkill = skills.find((s) => s.id === v) || null;
  const activity = Math.min(1, 0.22 + (voiceOn ? 0.35 : 0) + (pending ? 0.4 : 0));
  const navigate = useCallback((id) => { setView(id); if (id === "home") setOpenFolder(null); }, []);
  const title = activeSkill ? activeSkill.name : VIEW_NAMES[v];
  const trail = activeSkill?.folder ? `INÍCIO / ${activeSkill.folder.toUpperCase()} /` : v === "home" && openFolder ? `INÍCIO / ${openFolder.toUpperCase()} /` : "AI OS /";
  const voice = { active: voiceOn, busy: voiceBusy, onToggle: toggleVoice };

  const toggleFullscreen = useCallback(async () => {
    const next = !fullscreen;
    setFullscreen(next);
    try {
      if (next) {
        await document.documentElement.requestFullscreen?.();
      } else if (document.fullscreenElement) {
        await document.exitFullscreen?.();
      }
    } catch { /* noop — alguns navegadores/ambientes não suportam */ }
    kernel.call("toggle_fullscreen");
    pushLog({ level: "INFO", core: "Shell", msg: next ? "Tela cheia ativada." : "Tela cheia desativada." });
  }, [fullscreen, kernel, pushLog]);

  useEffect(() => {
    const onFsChange = () => setFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onFsChange);
    return () => document.removeEventListener("fullscreenchange", onFsChange);
  }, []);

  const toggleWidget = useCallback(async () => {
    const next = !widgetMode;
    setWidgetMode(next);
    await kernel.call("set_widget_mode", next);
    if (next) {
      await kernel.call("set_window_size", 380, 520);
      pushLog({ level: "INFO", core: "Shell", msg: "Modo widget ativado — janela compacta." });
    } else {
      await kernel.call("set_window_size", 1280, 760);
      pushLog({ level: "INFO", core: "Shell", msg: "Modo widget desativado — janela restaurada." });
    }
  }, [widgetMode, kernel, pushLog]);

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300..700&family=JetBrains+Mono:wght@300..700&display=swap');
        @keyframes aios-iris{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}
        @keyframes aios-breathe{0%,100%{opacity:.5}50%{opacity:1}}
        @keyframes aios-morph-a{0%,100%{border-radius:2.6rem 3.6rem 3rem 3.8rem/3.2rem 2.8rem 3.8rem 3rem}33%{border-radius:3.6rem 2.8rem 3.6rem 2.8rem/2.8rem 3.6rem 2.6rem 3.6rem}66%{border-radius:3rem 3.2rem 2.6rem 3.8rem/3.6rem 3rem 3.2rem 2.6rem}}
        @keyframes aios-morph-b{0%,100%{border-radius:3.8rem 2.8rem 3.6rem 3rem/3rem 3.8rem 2.8rem 3.6rem}50%{border-radius:2.8rem 3.8rem 3rem 3.6rem/3.8rem 2.8rem 3.6rem 3rem}}
        .aios-morph-a{animation:aios-morph-a 24s ease-in-out infinite}
        .aios-morph-b{animation:aios-morph-b 28s ease-in-out infinite}
        .aios-iris{background-size:300% 300%;animation:aios-iris 16s ease-in-out infinite}
        .aios-breathe{animation:aios-breathe 5s ease-in-out infinite}
        @media (prefers-reduced-motion:reduce){.aios-iris,.aios-breathe,.aios-morph-a,.aios-morph-b{animation:none}}
        .no-scrollbar{scrollbar-width:none}.no-scrollbar::-webkit-scrollbar{display:none}
        ::selection{background:var(--glow)}
      `}</style>
      <SvgDefs />

      <div data-theme={theme} className="relative isolate h-screen w-screen select-none overflow-hidden font-sans antialiased"
           style={{ ...THEMES[theme], fontFamily: DISPLAY, color: "var(--text)", background: "radial-gradient(120% 90% at 50% 100%,var(--bg-a) 0%,var(--bg-b) 75%)", transition: "color .5s" }}>
        <Atmosphere />
        <div className="flex h-full gap-4 p-4">
          <Menu expanded={menuOpen} onToggle={() => setMenuOpen((o) => !o)} view={v} onNavigate={navigate} skills={skills} groups={groups} voice={voice}
                consoleOpen={consoleOpen} onToggleConsole={() => setConsoleOpen((o) => !o)} openFolder={openFolder} setOpenFolder={setOpenFolder} />

          <main className="flex min-w-0 flex-1 flex-col gap-4">
            <Header theme={theme} onToggleTheme={toggleTheme} bridge={kernel.bridge} title={title} trail={trail} voiceOn={voiceOn}
                    fullscreen={fullscreen} onToggleFullscreen={toggleFullscreen} widgetMode={widgetMode} onToggleWidget={toggleWidget} />

            <div ref={wrapRef} className="flex min-h-0 flex-1 items-stretch">
              <AnimatePresence mode="wait" initial={false}>
                {v === "home" ? (
                  <motion.div key="home" className="h-full min-h-0 min-w-0 flex-1" {...PAGE}>
                    <Home groups={groups} messages={messages} logs={logs} theme={theme} onToggleTheme={toggleTheme} voice={voice} onNavigate={navigate}
                          consoleOpen={consoleOpen} onToggleConsole={() => setConsoleOpen((o) => !o)} activity={activity} openFolder={openFolder} setOpenFolder={setOpenFolder}
                          onSend={sendCommand} pending={pending} bridge={kernel.bridge} />
                  </motion.div>
                ) : v === "chat" ? (
                  <motion.div key="chat" className="h-full min-h-0 min-w-0 flex-1" {...PAGE}><ChatPanel messages={messages} pending={pending} onSend={sendCommand} effortMode={effortMode} onEffortChange={changeEffort} effortInfo={effortInfo} /></motion.div>
                ) : (
                  <motion.div key="split" className="flex h-full min-h-0 min-w-0 flex-1 items-stretch" {...PAGE}>
                    <div className="min-h-0 min-w-0 shrink-0" style={{ flexBasis: `${split}%` }}><ChatPanel messages={messages} pending={pending} onSend={sendCommand} /></div>
                    <div onPointerDown={() => setDrag(true)} role="separator" aria-orientation="vertical" aria-label="Redimensionar" className="mx-1 flex w-5 shrink-0 cursor-col-resize items-center justify-center">
                      <motion.span className="flex w-2.5 flex-col items-center justify-center gap-1.5 rounded-full" animate={{ height: drag ? 150 : 100 }} transition={SPRING}
                        style={{ background: "var(--chip)", border: "1px solid var(--edge)", boxShadow: drag ? "0 0 18px var(--glow)" : "none" }}>
                        {[0, 1, 2].map((i) => <i key={i} className="h-1 w-1 rounded-full" style={{ background: drag ? "var(--cyan)" : "var(--muted)" }} />)}
                      </motion.span>
                    </div>
                    <div className="min-h-0 min-w-0 flex-1">
                      <AnimatePresence mode="wait" initial={false}>
                        <motion.div key={`stage-${v}`} className="h-full" initial={{ opacity: 0, x: 50, scale: 0.96, filter: "blur(10px)" }} animate={{ opacity: 1, x: 0, scale: 1, filter: "blur(0px)" }} exit={{ opacity: 0, x: 50, scale: 0.96, filter: "blur(10px)" }} transition={SPRING}>
                          {activeSkill ? <SubGUIFrame skill={activeSkill} kernel={kernel} pushLog={pushLog} /> : <BrainStage skills={skills} onNavigate={navigate} activity={activity} />}
                        </motion.div>
                      </AnimatePresence>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            <KernelConsole logs={logs} open={consoleOpen} onToggle={() => setConsoleOpen((o) => !o)} />
          </main>
        </div>
      </div>

      {widgetMode && (
        <WidgetPopup kernel={kernel} theme={theme} voice={voice} onSend={sendCommand} pending={pending} messages={messages} pushLog={pushLog} />
      )}
    </>
  );
}
