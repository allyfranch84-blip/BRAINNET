import { useEffect, useState } from "react";

// Read-only polling; timed-out replies cannot replace newer snapshots.
export default function useKernelTelemetry(method, intervalMs = 3000) {
  const [snapshot, setSnapshot] = useState({ data: null, connection: "waiting" });

  useEffect(() => {
    let disposed = false;
    let pending = false;
    let timer;
    let generation = 0;
    const inFlight = new Set();
    const watchdogs = new Set();
    const poll = () => {
      if (disposed || pending || document.hidden || inFlight.size >= 2) return;
      const api = window.pywebview?.api;
      if (typeof api?.[method] !== "function") {
        setSnapshot({ data: null, connection: api ? "unavailable" : "waiting" });
        return;
      }
      pending = true;
      const request = ++generation;
      inFlight.add(request);
      const watchdog = setTimeout(() => {
        if (!disposed && request === generation) {
          console.warn(`[telemetry] ${method}: timeout aguardando Python`);
          pending = false;
          setSnapshot({ data: null, connection: "unavailable" });
        }
      }, 5000);
      watchdogs.add(watchdog);
      Promise.resolve().then(() => api[method]()).then((data) => {
        console.log(`[telemetry] ${method}:`, data);
        if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("Invalid telemetry");
        if (!disposed && request === generation) setSnapshot({ data, connection: "connected" });
      }).catch((error) => {
        console.warn(`[telemetry] ${method}: leitura indisponível`, error);
        if (!disposed && request === generation) setSnapshot({ data: null, connection: "unavailable" });
      }).finally(() => {
        clearTimeout(watchdog);
        watchdogs.delete(watchdog);
        inFlight.delete(request);
        if (request === generation) pending = false;
      });
    };
    const refresh = () => {
      if (!document.hidden) poll();
    };
    window.addEventListener("pywebviewready", refresh);
    document.addEventListener("visibilitychange", refresh);
    timer = setInterval(poll, intervalMs);
    poll();
    return () => {
      disposed = true;
      clearInterval(timer);
      watchdogs.forEach(clearTimeout);
      window.removeEventListener("pywebviewready", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [method, intervalMs]);

  return snapshot;
}
