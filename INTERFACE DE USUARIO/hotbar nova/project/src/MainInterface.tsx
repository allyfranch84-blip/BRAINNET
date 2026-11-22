import { useState } from 'react';
import Hotbar from '@/components/Hotbar';

function MainInterface() {
  const [isMicActive, setIsMicActive] = useState(false);
  const [log, setLog] = useState<string[]>([]);

  const pushLog = (msg: string) =>
    setLog((l) => [msg, ...l].slice(0, 6));

  return (
    <div className="relative min-h-screen overflow-hidden bg-[#05060a] text-white">
      {/* ambient background */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -top-32 left-1/2 h-[480px] w-[480px] -translate-x-1/2 rounded-full bg-[#7ff0e0]/10 blur-[120px]" />
        <div className="absolute bottom-0 left-1/4 h-[300px] w-[300px] rounded-full bg-violet-600/10 blur-[100px]" />
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.6) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.6) 1px, transparent 1px)',
            backgroundSize: '40px 40px',
          }}
        />
      </div>

      {/* header */}
      <header className="relative z-10 flex flex-col items-center justify-center px-6 pt-20 text-center">
        <span className="font-mono text-[10px] uppercase tracking-[0.4em] text-[#7ff0e0]/80">
          Dynamic Island · Hotbar
        </span>
        <h1 className="mt-4 max-w-2xl bg-gradient-to-b from-white to-white/60 bg-clip-text font-mono text-3xl font-bold tracking-tight text-transparent sm:text-5xl">
          A glass pill that feels native.
        </h1>
        <p className="mt-4 max-w-md font-mono text-sm text-gray-400">
          Hover the bar to expand it. Toggle the mic to see the live
          equalizer and neon glow.
        </p>
      </header>

      {/* status card */}
      <div className="relative z-10 mx-auto mt-12 flex max-w-md flex-col gap-3 px-6">
        <div className="flex items-center justify-between rounded-2xl border border-white/10 bg-white/5 px-5 py-4 backdrop-blur-md">
          <span className="font-mono text-xs uppercase tracking-widest text-gray-400">
            Microfone
          </span>
          <button
            onClick={() => {
              const next = !isMicActive;
              setIsMicActive(next);
              pushLog(next ? 'Mic ativado' : 'Mic desativado');
            }}
            className={`rounded-full border px-4 py-1.5 font-mono text-xs uppercase tracking-widest transition-all ${
              isMicActive
                ? 'border-[#7ff0e0]/60 bg-[#7ff0e0]/10 text-[#7ff0e0]'
                : 'border-white/15 text-gray-300 hover:border-white/40'
            }`}
          >
            {isMicActive ? 'Ativo' : 'Inativo'}
          </button>
        </div>

        <div className="rounded-2xl border border-white/10 bg-white/5 px-5 py-4 backdrop-blur-md">
          <span className="font-mono text-xs uppercase tracking-widest text-gray-400">
            Event log
          </span>
          <ul className="mt-3 space-y-1 font-mono text-xs text-gray-300">
            {log.length === 0 ? (
              <li className="text-gray-600">// sem eventos</li>
            ) : (
              log.map((entry, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-[#7ff0e0]">›</span>
                  <span>{entry}</span>
                </li>
              ))
            )}
          </ul>
        </div>
      </div>

      {/* the hotbar */}
      <Hotbar
        isMicActive={isMicActive}
        onMic={() => {
          const next = !isMicActive;
          setIsMicActive(next);
          pushLog(next ? 'Mic ativado' : 'Mic desativado');
        }}
        onSearch={() => pushLog('Busca aberta')}
        onExpand={() => pushLog('GUI expandida')}
        onClose={() => pushLog('Sessão encerrada')}
      />
    </div>
  );
}

export default MainInterface;
