import React, { useEffect, useState } from "react";

async function call(method, ...args) {
  if (typeof window.pywebview?.api?.[method] !== "function") throw new Error("Kernel desconectado");
  return window.pywebview.api[method](...args);
}
const button = "rounded-xl border border-cyan-200/25 bg-cyan-200/10 px-3 py-2 text-xs text-cyan-100 disabled:opacity-40";

export default function RoutesPanel() {
  const [routes, setRoutes] = useState([]);
  const [versions, setVersions] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const refresh = async () => setRoutes(await call("get_routes"));
  const run = async (operation) => {
    setBusy(true); setError("");
    try { await operation(); }
    catch (failure) { setError(failure?.message || String(failure)); }
    finally { setBusy(false); }
  };
  useEffect(() => {
    let alive = true;
    call("get_routes").then((rows) => { if (alive) setRoutes(rows); }).catch((failure) => { if (alive) setError(failure.message); });
    return () => { alive = false; };
  }, []);
  const manage = (action, route) => run(async () => {
    const result = await call("manage_route", action, route.context_key);
    if (!result?.ok) throw new Error(result?.error || "Operação não confirmada");
    setVersions(null); await refresh();
  });
  return <section aria-label="Rotas e Histórico" className="rounded-3xl border border-cyan-200/20 bg-slate-950/70 p-5 backdrop-blur-xl">
    <div className="mb-4 flex items-center justify-between gap-3"><h3>Rotas e Histórico</h3><button className={button} disabled={busy} onClick={() => run(refresh)}>Atualizar Rotas</button></div>
    {error && <p role="alert" className="mb-3 text-sm text-amber-200">{error}</p>}
    {!routes.length && <p className="text-sm text-slate-400">Nenhuma rota ativa carregada.</p>}
    <ul className="space-y-3">{routes.map((route) => <li key={route.context_key} className="rounded-xl border border-white/10 p-3">
      <p className="break-words text-sm">{route.intent} · v{route.version}</p><p className="mb-2 break-all text-xs text-slate-400">{route.context_key}</p>
      <div className="flex flex-wrap gap-2">
        <button className={button} disabled={busy} onClick={() => run(async () => setVersions({ key: route.context_key, rows: await call("get_route_versions", route.context_key) }))}>Ver Versões</button>
        <button className={button} disabled={busy} onClick={() => manage("deactivate", route)}>Desativar</button>
        <button className={button} disabled={busy} onClick={() => manage("revert", route)}>Reverter</button>
      </div>
    </li>)}</ul>
    {versions && <div className="mt-4 rounded-xl border border-violet-200/20 p-3"><p className="mb-2 break-all text-sm">{versions.key}</p>{versions.rows.map((row) => <p key={row.version} className="text-xs text-slate-300">v{row.version} · {new Date(row.created_at * 1000).toLocaleString("pt-BR")} · {row.is_active ? "Ativa" : "Histórica/inativa"}</p>)}</div>}
  </section>;
}
