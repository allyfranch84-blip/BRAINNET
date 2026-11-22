import React, { useEffect } from "react";

const labels = ["Definição disponível · execução não ensinada", "Execução ensinada · não validada", "Execução validada"];

export default function ConceptDetailsModal({ concept, onClose }) {
  useEffect(() => {
    const escape = (event) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [onClose]);
  return <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/75 p-4">
    <section role="dialog" aria-modal="true" aria-labelledby="concept-details-title" className="max-h-[85vh] w-full max-w-xl overflow-y-auto rounded-3xl border border-cyan-200/25 bg-slate-950/95 p-6 text-slate-100 shadow-xl backdrop-blur-xl">
      <div className="mb-5 flex items-start justify-between gap-3"><h3 id="concept-details-title" className="break-words text-lg">{concept.id}</h3><button autoFocus type="button" aria-label="Fechar detalhes" className="rounded-lg border border-white/20 px-3 py-1" onClick={onClose}>✕</button></div>
      <dl className="space-y-4 text-sm">
        <div><dt className="text-xs text-cyan-200">Definição Completa</dt><dd className="mt-1 whitespace-pre-wrap break-words text-slate-300">{concept.definicao || "Não informada"}</dd></div>
        <div><dt className="text-xs text-cyan-200">Sinônimos</dt><dd className="mt-1 text-slate-300">{concept.sinonimos?.length ? concept.sinonimos.join(", ") : "Não informados"}</dd></div>
        <div><dt className="text-xs text-cyan-200">ID do vetor FHRR (SHA-256)</dt><dd className="mt-1 break-all font-mono text-xs text-slate-400">{concept.vector_id}</dd></div>
        <div><dt className="text-xs text-cyan-200">Status de Validação</dt><dd className="mt-1 text-slate-300">{labels[concept.status] || "Indisponível"}</dd></div>
      </dl>
    </section>
  </div>;
}
