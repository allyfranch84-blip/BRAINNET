import React from "react";
import WorldModelWidget from "./WorldModelWidget";
import MetacognitionGauge from "./MetacognitionGauge";
import useKernelTelemetry from "./useKernelTelemetry";

class TelemetryBoundary extends React.Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error, info) { console.error("[telemetry] Falha ao renderizar painel", error, info); }
  render() {
    if (this.state.failed) return <div role="alert" className="rounded-2xl border border-amber-200/20 bg-slate-950/70 p-5 text-sm text-slate-300">Nenhum dado de telemetria disponível.</div>;
    return this.props.children;
  }
}

export default function TelemetryDashboard({ task, bridge }) {
  const runtime = useKernelTelemetry('get_runtime_telemetry', 5000);
  const data = runtime.connection === 'connected' && runtime.data?.available ? runtime.data : null;
  const hw = data?.hardware;
  const ollama = data?.inference?.ollama;
  const bytes = value => typeof value === 'number' && Number.isFinite(value) ? `${(value / 1073741824).toFixed(2)} GiB` : 'Não disponível';
  const percent = value => typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(1)}%` : 'Não disponível';
  const budget = task?.budget;
  const show = value => value === null || value === undefined ? 'Não disponível' : String(value);
  return <div className="h-full min-h-0 overflow-y-auto p-4 text-slate-100 sm:p-6" aria-label="Painel de Telemetria">
    <header className="mb-6"><h2 className="text-2xl font-light">Telemetria</h2><p className="mt-2 text-sm text-slate-400">Estado das integrações e uso do sistema.</p></header>
    <section aria-label="Hardware" className="mb-4 rounded-2xl border border-cyan-300/20 bg-slate-950/70 p-4 text-sm">
      <h2 className="mb-2 font-semibold">Hardware</h2>
      <p className="text-xs text-slate-400">{data ? `Fonte: ${data.source} · ${data.stale ? 'Dado desatualizado' : 'Coletado'} ${new Date(data.timestamp * 1000).toLocaleTimeString('pt-BR')}` : 'Coletor indisponível ou aguardando primeira amostra'}</p>
      <div>CPU total: {percent(hw?.cpu_total_pct)} · Processo BRAINNET: {percent(hw?.cpu_process_pct)}</div>
      <div>RAM total: {bytes(hw?.ram_total_bytes)} · usada: {bytes(hw?.ram_used_bytes)} · disponível: {bytes(hw?.ram_available_bytes)}</div>
      <div>RAM processo: {bytes(hw?.process_rss_bytes)} · GPU: {percent(hw?.gpu_pct)} · VRAM usada: {bytes(hw?.vram_used_bytes)}</div>
      <div>VRAM disponível: {bytes(hw?.vram_available_bytes)} · Temperatura: {hw?.temperature_c ?? 'Não disponível'} · {hw?.gpu_source || 'Fonte GPU indisponível'}</div>
    </section>
    <section aria-label="Inferência e Kernel" className="mb-4 rounded-2xl border border-cyan-300/20 bg-slate-950/70 p-4 text-sm">
      <h2 className="mb-2 font-semibold">Inferência e Kernel</h2>
      <p>Kernel: {data ? (data.kernel?.running ? 'Em execução' : 'Parado') : 'Não disponível'} · Tarefas ativas: {data?.kernel?.active_tasks?.length ?? 'Não disponível'}</p>
      <p>Tarefas recentes (máximo 32): {data?.kernel?.recent_tasks?.length ?? 'Não disponível'} · Operações não confirmadas nas recentes: {data?.kernel?.recent_tasks?.every(item => typeof item.inflight === 'number') ? data.kernel.recent_tasks.reduce((total, item) => total + item.inflight, 0) : 'Não disponível'}</p>
      <p>Ollama: {!ollama ? 'Não disponível' : ollama.available ? `Disponível · ${ollama.latency_ms} ms` : 'Indisponível'} · Fila: Não disponível</p>
      <p>Modelos residentes: {ollama?.available ? (ollama.models.length ? ollama.models.map(m => `${m.name || 'sem nome'} (${bytes(m.size_bytes)}; VRAM ${bytes(m.vram_bytes)}; expira ${m.expires_at || 'desconhecido'})`).join(', ') : 'Nenhum informado') : 'Não disponível'}</p>
      <p>Processos de inferência: {data?.inference?.processes ? (data.inference.processes.length ? data.inference.processes.map(p => `${p.name} #${p.pid} (${bytes(p.rss_bytes)})`).join(', ') : 'Nenhum encontrado') : 'Não disponível'}</p>
    </section>
    <section aria-label="Tarefa do Kernel" className="mb-4 rounded-2xl border border-cyan-300/20 bg-slate-950/70 p-4 text-sm">
      <h2 className="mb-2 font-semibold">Tarefa do Kernel</h2>
      {!task ? <p>{bridge === 'pywebview' ? 'Transporte conectado; nenhuma telemetria de tarefa recebida nesta sessão.' : 'Kernel indisponível; aguardando conexão real.'}</p> :
        <dl className="grid gap-2 sm:grid-cols-2">
          <div>ID: {show(budget?.task_id)}</div><div>Estado: {show(task.phase)} · {show(budget?.task_state)}</div>
          <div>Modo solicitado: {show(task.configured)}</div><div>Modo efetivo: {show(task.effective)}</div>
          <div>Modelo: {show(budget?.selected_model)}</div><div>Backend: {show(budget?.backend)}</div>
          <div>Prazo restante na atualização: {budget?.remaining_s == null ? 'Não disponível' : `${Number(budget.remaining_s).toFixed(1)} s`}</div>
          <div>Planejamento / inferências / visão: {show(budget?.planning_steps_used)} / {show(budget?.inference_calls_used)} / {show(budget?.visual_iterations_used)}</div>
          <div>Tokens estimados: {show(budget?.token_usage?.estimated)}</div><div>Tokens reportados: {show(budget?.token_usage?.reported)}</div>
          <div>Operações pendentes ou não confirmadas: {show(budget?.inflight)}</div><div>Resultado: {show(task.result_status)} · Objetivo: {show(task.goal_state)}</div>
          <div>Falha: {task.error_type ? show(task.error_type) : 'Não disponível — nenhuma falha atribuída'}</div>
        </dl>}
    </section>
    <TelemetryBoundary>
      <div className="flex flex-wrap items-start gap-4"><WorldModelWidget /><MetacognitionGauge /></div>
    </TelemetryBoundary>
  </div>;
}
