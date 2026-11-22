import React from "react";
import useKernelTelemetry from "./useKernelTelemetry";
import IntegrationStatus from "./IntegrationStatus";

const finite = (value) => typeof value === "number" && Number.isFinite(value);

export default function WorldModelWidget() {
  const { data, connection } = useKernelTelemetry("get_world_model_status");
  const connected = connection === "connected" && data != null && data.available !== false;
  const mse = connected && finite(data?.mse) && data.mse >= 0 ? data.mse : null;
  const confidence = connected && finite(data?.policy_confidence) && data.policy_confidence >= 0 && data.policy_confidence <= 1
    ? data.policy_confidence : null;
  const transitions = connected && Number.isSafeInteger(data?.transitions) && data.transitions >= 0 ? data.transitions : null;
  const status = !connected ? (connection === "waiting" ? "Aguardando kernel" : "Telemetria indisponível")
    : mse === null && confidence === null ? "Em espera" : "Observando";
  const readAt = connected && finite(data?.updated_at) ? new Date(data.updated_at * 1000).toLocaleTimeString("pt-BR") : null;

  return (
    <section aria-label="Telemetria do World Model" className="min-w-0 flex-[1_1_24rem] rounded-2xl border border-cyan-300/20 bg-slate-950/70 px-4 py-3 text-slate-100 shadow-[0_0_24px_rgba(34,211,238,0.06)] backdrop-blur-xl">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <h2 className="text-[10px] font-semibold uppercase tracking-[0.22em] text-cyan-200/80">Telemetria cognitiva</h2>
        <span className="text-[10px] text-slate-400">{status}{readAt ? ` · leitura ${readAt}` : ""}</span>
      </div>
      {mse === null && confidence === null && transitions === null && <p role="status" className="mb-3 text-sm text-slate-400">Nenhum dado de telemetria disponível.</p>}
      <dl className="grid grid-cols-1 gap-2 sm:grid-cols-3 sm:gap-4">
        <div>
          <dt className="text-[10px] uppercase tracking-wider text-slate-400">World Model · MSE</dt>
          <dd className="mt-1 truncate font-mono text-sm tabular-nums text-cyan-100" title="Última MSE real de treino, medida antes da atualização">
            {mse === null ? (connected ? "Não treinado" : "--") : mse.toLocaleString("pt-BR", { minimumFractionDigits: 4, maximumFractionDigits: 4 })}
          </dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-wider text-slate-400">Policy PPO · confiança</dt>
          <dd className="mt-1 truncate font-mono text-sm tabular-nums text-violet-100">
            {confidence === null ? (connected ? "Sem inferência" : "--") : `${(confidence * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`}
          </dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-wider text-slate-400">Transições coletadas</dt>
          <dd className="mt-1 font-mono text-sm tabular-nums text-emerald-100">{transitions === null ? "--" : transitions.toLocaleString("pt-BR")}</dd>
        </div>
      </dl>
      {connected && data?.errors?.length > 0 && <p className="mt-2 text-[10px] text-amber-200/80">Algumas métricas estão indisponíveis.</p>}
      <IntegrationStatus />
    </section>
  );
}
