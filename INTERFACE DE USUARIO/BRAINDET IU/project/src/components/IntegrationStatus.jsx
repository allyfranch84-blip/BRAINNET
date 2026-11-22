import React from "react";
import useKernelTelemetry from "./useKernelTelemetry";

export default function IntegrationStatus() {
  const health = useKernelTelemetry("get_diagnostics", 3000);
  const usage = useKernelTelemetry("get_usage_report", 3000);
  const labels = { ollama: "Ollama", ocr: "OCR", extension: "Extensão", voice: "Voz" };
  const report = usage.connection === "connected" ? usage.data : null;
  return <div className="mt-3 border-t border-white/10 pt-3">
    <div aria-label="Diagnóstico de integrações" className="flex flex-wrap gap-2">{Object.entries(labels).map(([key, label]) => {
      const value = health.connection === "connected" ? health.data?.[key] : null;
      const status = typeof value?.ok === "boolean" ? value : null;
      return <span key={key} title={status?.detail || label} className={`rounded-full border px-2 py-1 text-[10px] ${!status ? "border-slate-500/30 text-slate-400" : status.ok ? "border-green-300/20 text-green-200" : "border-red-300/20 text-red-200"}`}>{label}: {!status ? "--" : status.ok ? "Disponível" : "Indisponível"}</span>;
    })}</div>
    <p className="mt-2 text-xs text-slate-300">Execuções observadas: {report?.total_executions ?? "--"} · Sucesso: {Number.isFinite(report?.success_rate) ? `${report.success_rate.toFixed(1)}%` : "--"} · Latência média: {Number.isFinite(report?.average_latency_ms) ? `${report.average_latency_ms.toFixed(1)} ms` : "--"}</p>
  </div>;
}
