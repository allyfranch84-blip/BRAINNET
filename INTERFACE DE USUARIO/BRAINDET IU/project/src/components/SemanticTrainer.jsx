import React, { useCallback, useEffect, useRef, useState } from "react";
import RoutesPanel from "./RoutesPanel";
import ConceptDetailsModal from "./ConceptDetailsModal";

const panel = "min-w-0 rounded-3xl border border-cyan-200/20 bg-slate-950/70 p-5 shadow-[0_0_30px_rgba(127,240,224,0.04)] backdrop-blur-xl";
const field = "w-full rounded-xl border border-white/15 bg-slate-900/90 px-3 py-3 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:border-cyan-200/70 focus:ring-2 focus:ring-cyan-200/15 disabled:opacity-50";
const button = "rounded-xl border border-cyan-200/30 bg-cyan-200/10 px-4 py-2.5 text-sm font-medium text-cyan-100 transition-colors hover:bg-cyan-200/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-200 disabled:cursor-not-allowed disabled:opacity-40";
const learningLabels = { api: "Buscando na API...", browser: "Abrindo Navegador...", extracting: "Extraindo definição...", local: "Consultando Qwen local...", saving: "Salvando Conceito..." };

async function callKernel(method, ...args) {
  const api = window.pywebview?.api;
  if (typeof api?.[method] !== "function") {
    throw new Error("Abra esta interface pelo kernel para acessar a rede semântica.");
  }
  return api[method](...args);
}

export default function SemanticTrainer() {
  const [concepts, setConcepts] = useState([]);
  const [tab, setTab] = useState("concepts");
  const [concept, setConcept] = useState("");
  const [definition, setDefinition] = useState("");
  const [origin, setOrigin] = useState("");
  const [learningStage, setLearningStage] = useState("api");
  const activeLearnRequest = useRef(null);
  const [first, setFirst] = useState("");
  const [second, setSecond] = useState("");
  const [composition, setComposition] = useState("");
  const [details, setDetails] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [teaching, setTeaching] = useState(null);
  const [lessonInput, setLessonInput] = useState("");
  const [lessonReply, setLessonReply] = useState("");
  const alive = useRef(false);
  const working = useRef(false);

  const refreshData = useCallback(async () => {
    const rows = await callKernel("get_semantic_concepts");
    if (!Array.isArray(rows) || rows.some((row) => typeof row?.id !== "string")) {
      throw new Error("O kernel retornou uma lista de conceitos inválida.");
    }
    if (!alive.current) return;
    setConcepts(rows);
    setFirst((previous) => rows.some((row) => row.id === previous) ? previous : rows[0]?.id || "");
    setSecond((previous) => rows.some((row) => row.id === previous) ? previous : rows[1]?.id || rows[0]?.id || "");
  }, []);

  const run = useCallback(async (name, operation) => {
    if (working.current) return;
    working.current = true;
    setBusy(name);
    setError("");
    try {
      await operation();
    } catch (failure) {
      if (alive.current) setError(failure?.message || String(failure));
    } finally {
      working.current = false;
      if (alive.current) setBusy("");
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    const load = () => run("list", refreshData);
    const progress = (event) => {
      if (event.detail?.request_id !== activeLearnRequest.current || !activeLearnRequest.current) return;
      if (learningLabels[event.detail.stage]) setLearningStage(event.detail.stage);
    };
    window.addEventListener("pywebviewready", load);
    window.addEventListener("aios:concept_learning", progress);
    load();
    return () => {
      alive.current = false;
      window.removeEventListener("pywebviewready", load);
      window.removeEventListener("aios:concept_learning", progress);
    };
  }, [refreshData, run]);

  const learn = (event) => {
    event.preventDefault();
    const name = concept.trim();
    if (!name) return;
    run("learn", async () => {
      setDefinition("");
      setOrigin("");
      const requestId = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
      activeLearnRequest.current = requestId;
      setLearningStage("api");
      let result;
      try { result = await callKernel("learn_concept_web", name, requestId); }
      finally { activeLearnRequest.current = null; }
      if (result?.ok !== true) throw new Error(result?.error || "O kernel não confirmou o aprendizado.");
      if (typeof result.definicao !== "string" || !result.definicao.trim()) throw new Error("O kernel não confirmou uma definição.");
      if (alive.current) {
        setDefinition(result.definicao);
        setOrigin(result.origem === "llm_local" ? "Definição do modelo local · sem validação web" : result.origem === "browser" ? "Definição extraída do navegador" : result.origem === "web" ? "Definição extraída das fontes web" : "Conceito já salvo no banco");
      }
      await refreshData();
    });
  };

  const compose = (event) => {
    event.preventDefault();
    if (!first || !second) return;
    run("compose", async () => {
      setComposition("");
      const saved = await callKernel("compose_concepts", first, second);
      if (saved?.ok !== true) throw new Error(saved?.error || "Composição não salva.");
      if (alive.current) setComposition(saved.synthesis_ok && saved.definicao
        ? `A IA concluiu que:\n\n${saved.definicao}`
        : `Conceito '${saved.id}' criado. Síntese pendente: ${saved.warning || "modelo indisponível"}`);
      await refreshData();
    });
  };

  const openDetails = (item) => run("details", async () => {
    const result = await callKernel("get_semantic_concept_details", item.id);
    if (!result?.ok) throw new Error(result?.error || "Detalhes indisponíveis.");
    if (alive.current) setDetails(result);
  });

  const startTeaching = (item) => run("teach", async () => {
    const result = await callKernel("teach_semantic_concept", item.id);
    if (!result?.ok) throw new Error(result?.error || "Professor indisponível.");
    if (alive.current) { setTeaching(item.id); setLessonReply(result.reply); setLessonInput(""); }
  });

  const sendLesson = (text) => run("teach", async () => {
    const result = await callKernel("send_command", text);
    if (typeof result?.reply !== "string") throw new Error("Resposta do Professor inválida.");
    if (alive.current) { setLessonReply(result.reply); setLessonInput(""); }
    await refreshData();
    if (text === "/cancelar" && alive.current) setTeaching(null);
  });

  return (
    <section aria-label="Treinamento da rede semântica" aria-busy={Boolean(busy)} className="h-full min-h-0 overflow-y-auto p-4 text-slate-100 sm:p-6" style={{ fontFamily: "'Space Grotesk','Helvetica Neue',Helvetica,Arial,sans-serif" }}>
      <header className="mb-6">
        <p className="text-[10px] uppercase tracking-[0.24em] text-cyan-200/70">Conhecimento · conceitos · composição</p>
        <h2 className="mt-2 text-2xl font-light sm:text-3xl">Rede Semântica</h2>
        <p className="mt-2 text-sm text-slate-400">Aprenda definições e conecte conceitos. A execução física é ensinada separadamente no Professor.</p>
      </header>
      {error && <p role="alert" className="mb-4 rounded-xl border border-amber-200/25 bg-amber-200/5 p-3 text-sm text-amber-100">{error}</p>}
      {details && <ConceptDetailsModal concept={details} onClose={() => setDetails(null)} />}
      {teaching && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
        <section role="dialog" aria-modal="true" aria-labelledby="semantic-teaching-title" className={`${panel} w-full max-w-xl`}>
          <h3 id="semantic-teaching-title" className="text-lg">Ensinar: {teaching}</h3>
          <p aria-live="polite" className="my-4 whitespace-pre-wrap text-sm text-cyan-100">{lessonReply}</p>
          <form onSubmit={(event) => { event.preventDefault(); if (lessonInput.trim()) sendLesson(lessonInput.trim()); }}>
            <label htmlFor="semantic-lesson" className="text-xs text-slate-300">Propósito ou passos separados por ponto e vírgula (;). Os passos serão executados.</label>
            <textarea autoFocus id="semantic-lesson" className={`${field} mt-2`} value={lessonInput} disabled={Boolean(busy)} onChange={(event) => setLessonInput(event.target.value)} />
            <div className="mt-3 flex flex-wrap gap-2">
              <button className={button} disabled={Boolean(busy) || !lessonInput.trim()}>Enviar</button>
              {["/voltar", "/fim", "/cancelar"].map((command) => <button type="button" key={command} className={button} disabled={Boolean(busy)} onClick={() => sendLesson(command)}>{command}</button>)}
              <button type="button" className={button} disabled={Boolean(busy)} onClick={() => setTeaching(null)}>Fechar painel</button>
            </div>
          </form>
        </section>
      </div>}
      <div role="tablist" aria-label="Rede Semântica" className="mb-4 flex gap-2">
        <button type="button" role="tab" aria-selected={tab === "concepts"} className={button} onClick={() => { setTab("concepts"); run("list", refreshData); }}>Conceitos</button>
        <button type="button" role="tab" aria-selected={tab === "routes"} className={button} onClick={() => setTab("routes")}>Rotas e Histórico</button>
      </div>
      {tab === "routes" && <RoutesPanel />}
      <div className={tab === "routes" ? "hidden" : "grid grid-cols-1 gap-4 xl:grid-cols-3"}>
        <section className={panel} aria-labelledby="semantic-list-title">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h3 id="semantic-list-title" className="text-lg font-medium">Conceitos <span className="ml-1 text-sm text-slate-400">{concepts.length}</span></h3>
            <button type="button" className={button} disabled={Boolean(busy)} onClick={() => run("list", refreshData)}>{busy === "list" ? "Atualizando…" : "Atualizar Lista"}</button>
          </div>
          {concepts.length === 0 ? <p className="text-sm text-slate-400">{busy === "list" ? "Consultando o banco…" : "Nenhum conceito carregado. Aprenda um conceito ou atualize a lista."}</p> : (
            <ul className="max-h-[55vh] space-y-2 overflow-y-auto pr-1">
              {concepts.map((item) => (
                <li key={item.id} className="rounded-xl border border-white/10 bg-white/[0.025] p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="break-words text-sm font-medium">{item.id}</span>
                    <span className={`rounded-full px-2 py-1 text-xs ${item.status === 2 ? "bg-green-400/10 text-green-200" : item.status === 1 ? "bg-orange-400/10 text-orange-200" : "bg-yellow-400/10 text-yellow-200"}`}>
                      {item.status === 2 ? "🟢 Habilidade Validada" : item.status === 1 ? "🟠 Habilidade (Não Validada)" : "🟡 Conceito"}
                    </span>
                    <span className={`text-[10px] uppercase tracking-wider ${item.is_primario ? "text-cyan-200" : "text-violet-200"}`}>{item.is_primario ? "Primário" : "Composto"}</span>
                  </div>
                  {item.definicao && <p className="mt-2 whitespace-pre-wrap break-words text-xs leading-relaxed text-slate-400">{item.definicao}</p>}
                  <button type="button" className={`${button} mt-3 mr-2`} disabled={Boolean(busy)} onClick={() => openDetails(item)}>Ver Detalhes</button>
                  {(item.status ?? 0) === 0 && <button type="button" className={`${button} mt-3`} disabled={Boolean(busy)} onClick={() => startTeaching(item)}>Ensinar Passos Físicos</button>}
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className={panel} aria-labelledby="semantic-learn-title">
          <h3 id="semantic-learn-title" className="text-lg font-medium">Auto-Professor</h3>
          <p className="mb-5 mt-2 text-sm text-slate-400">Uma definição curta, extraída das fontes encontradas na web.</p>
          <form onSubmit={learn} className="space-y-3">
            <label htmlFor="semantic-concept" className="block text-xs text-slate-300">Pesquisar Conceito na Web</label>
            <input id="semantic-concept" className={field} placeholder="Ex.: aplicativo" maxLength={256} value={concept} disabled={Boolean(busy)} onChange={(event) => { setConcept(event.target.value); setDefinition(""); }} />
            <button type="submit" className={button} disabled={Boolean(busy) || !concept.trim()}>{busy === "learn" ? learningLabels[learningStage] : "Aprender"}</button>
          </form>
          <div aria-live="polite" className="mt-5 whitespace-pre-wrap break-words text-sm leading-relaxed text-cyan-50">{definition}</div>
          {definition && origin && <p className="mt-2 text-xs text-slate-400">{origin}</p>}
        </section>
        <section className={panel} aria-labelledby="semantic-compose-title">
          <h3 id="semantic-compose-title" className="text-lg font-medium">Composição</h3>
          <p className="mb-5 mt-2 text-sm text-slate-400">Combine dois conceitos aprendidos. A ordem define o novo conceito.</p>
          <form onSubmit={compose} className="space-y-3">
            <label htmlFor="semantic-first" className="block text-xs text-slate-300">Conceito A</label>
            <select id="semantic-first" className={field} value={first} disabled={Boolean(busy) || !concepts.length} onChange={(event) => { setFirst(event.target.value); setComposition(""); }}>
              {!concepts.length && <option value="">Aprenda um conceito primeiro</option>}
              {concepts.map((item) => <option key={item.id} value={item.id}>{item.id}</option>)}
            </select>
            <label htmlFor="semantic-second" className="block text-xs text-slate-300">Conceito B</label>
            <select id="semantic-second" className={field} value={second} disabled={Boolean(busy) || !concepts.length} onChange={(event) => { setSecond(event.target.value); setComposition(""); }}>
              {!concepts.length && <option value="">Aprenda um conceito primeiro</option>}
              {concepts.map((item) => <option key={item.id} value={item.id}>{item.id}</option>)}
            </select>
            <button type="submit" className={button} disabled={Boolean(busy) || !first || !second}>{busy === "compose" ? "Compondo…" : "Compor Conceitos"}</button>
          </form>
          {composition && <div role="status" className="mt-5 whitespace-pre-wrap break-words rounded-2xl border border-violet-200/25 bg-violet-200/5 p-4 text-sm leading-relaxed text-violet-100">{composition}</div>}
        </section>
      </div>
    </section>
  );
}
