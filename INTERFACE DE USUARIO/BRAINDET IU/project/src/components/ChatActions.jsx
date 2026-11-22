import React, { useEffect, useRef, useState } from "react";

const actionStyle = { color: "var(--cyan)", border: "1px solid var(--edge)", background: "var(--chip)" };

export function useChatInputFocus(messages, pending) {
  const inputRef = useRef(null);
  useEffect(() => {
    if (pending) return undefined;
    const timer = setTimeout(() => {
      if (!document.hasFocus() || document.querySelector('[aria-modal="true"]') || Date.now() < (window.__brainnetNoFocusUntil || 0)) return;
      inputRef.current?.focus({ preventScroll: true });
    }, 0);
    return () => clearTimeout(timer);
  }, [messages, pending]);
  return inputRef;
}

export function CopyButton({ text, label = "📋 Copiar" }) {
  const [status, setStatus] = useState("");
  const copy = async () => {
    try {
      if (window.pywebview?.api?.copy_text) {
        const result = await window.pywebview.api.copy_text(text);
        if (!result?.ok) throw new Error(result?.log || "Não foi possível copiar.");
      } else {
        await navigator.clipboard.writeText(text);
      }
      setStatus("Copiado");
    } catch (error) { setStatus(error?.message || "Falha ao copiar"); }
  };
  return <span><button type="button" className="rounded-full px-3 py-1 text-xs" style={actionStyle} onClick={copy}>{label}</button>{status && <span role="status" className="ml-2 text-xs">{status}</span>}</span>;
}

export function MessageActions({ text, onSend, pending }) {
  return <div className="mt-2 flex flex-wrap gap-2" aria-label="Ações da resposta">
    <CopyButton text={text} />
    <button type="button" title="Ler tudo" className="rounded-full px-3 py-1 text-xs" style={actionStyle} disabled={pending} onClick={() => onSend(`/leia ${text}`)}>🔊 Ler Tudo</button>
    <button type="button" title="Pesquisar resposta" className="rounded-full px-3 py-1 text-xs" style={actionStyle} disabled={pending} onClick={() => onSend(`/pesquise ${text}`)}>🔍 Pesquisar</button>
  </div>;
}

export function SearchButton({ isSearchMode, toggle, pending }) {
  return <button type="button" aria-label="Modo de pesquisa" aria-pressed={isSearchMode} title="Ativar/desativar pesquisa" disabled={pending} className="grid h-10 w-10 shrink-0 place-items-center rounded-full" style={{ ...actionStyle, color: isSearchMode ? "#4ade80" : "var(--cyan)", boxShadow: isSearchMode ? "0 0 14px #4ade8040" : "none" }} onClick={toggle}>🔍</button>;
}
