import React from "react";
import useKernelTelemetry from "./useKernelTelemetry";

const STATES = {
  ALIGNED: { label: "Alinhado", orb: "from-emerald-200 via-emerald-400 to-emerald-800 shadow-[0_0_22px_rgba(52,211,153,0.45)]", text: "text-emerald-200" },
  UNCERTAIN: { label: "Incerteza", orb: "from-amber-100 via-amber-400 to-amber-800 shadow-[0_0_22px_rgba(251,191,36,0.35)]", text: "text-amber-200" },
  OVERCONFIDENT: { label: "Sobreconfiante", orb: "from-rose-200 via-rose-500 to-rose-900 shadow-[0_0_22px_rgba(244,63,94,0.45)]", text: "text-rose-200" },
};

export default function MetacognitionGauge() {
  const { data, connection } = useKernelTelemetry("get_metacognition_status");
  const connected = connection === "connected" && data?.available !== false;
  const samples = connected && Number.isSafeInteger(data?.samples) ? data.samples : 0;
  const error = connected && typeof data?.calibration_error === "number" && Number.isFinite(data.calibration_error)
    ? data.calibration_error : null;
  const state = connected && samples > 0 && error !== null ? STATES[data?.state] || STATES.UNCERTAIN : STATES.UNCERTAIN;
  const detail = !connected ? (connection === "waiting" ? "Aguardando kernel" : "Sem conexão")
    : samples === 0 ? "Sem amostras" : `Δ ${error === null ? "—" : error.toLocaleString("pt-BR", { signDisplay: "always", maximumFractionDigits: 3 })} · n=${samples}`;

  return (
    <section role="status" aria-live="polite" aria-label={`Metacognição: ${state.label}. ${detail}`} title="Erro de calibração = acertos reais − confiança alegada. Valores negativos indicam sobreconfiança."
      className="group flex shrink-0 items-center gap-3 rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-slate-100 backdrop-blur-xl">
      <span aria-hidden="true" className={`relative block h-10 w-10 rounded-full border border-white/20 bg-gradient-to-br transition-transform motion-safe:group-hover:-translate-y-0.5 ${state.orb}`}>
        <span className="absolute left-2 top-1.5 h-2.5 w-3 rounded-full bg-white/70 blur-[2px]" />
      </span>
      <div>
        <h2 className="text-[10px] uppercase tracking-wider text-slate-400">Metacognição</h2>
        <p className={`mt-0.5 text-xs font-medium ${state.text}`}>{state.label}</p>
        <p className="mt-0.5 font-mono text-[10px] tabular-nums text-slate-400">{detail}</p>
      </div>
    </section>
  );
}
