import React, { useEffect, useRef, useState } from "react";

export default function VoiceToast() {
  const [text, setText] = useState("");
  const timer = useRef(null);
  useEffect(() => {
    const receive = (event) => {
      if (typeof event.detail?.text !== "string") return;
      clearTimeout(timer.current);
      setText(event.detail.text);
      timer.current = setTimeout(() => setText(""), 3000);
    };
    window.addEventListener("aios:voice_transcription", receive);
    return () => { window.removeEventListener("aios:voice_transcription", receive); clearTimeout(timer.current); };
  }, []);
  if (!text) return null;
  return <div role="status" aria-live="polite" className="pointer-events-none fixed left-1/2 top-1/3 z-[100] max-h-[40vh] w-[min(90vw,40rem)] -translate-x-1/2 overflow-hidden rounded-2xl border border-cyan-200/30 bg-slate-950/90 p-5 text-center text-slate-100 shadow-xl backdrop-blur-xl">
    <p className="mb-2 text-xs uppercase tracking-wider text-cyan-200">🎙️ Ouvi você dizer</p><p className="whitespace-pre-wrap break-words text-sm">{text}</p>
  </div>;
}
