# -*- coding: utf-8 -*-
"""P51.1: chat layout, safe Markdown, voice preferences and local conversation archive."""
from pathlib import Path
from datetime import datetime
import argparse, json, subprocess, shutil

ARCHIVE = r'''
"""Conversation archive, separate from motor authorization and user notes."""
import sqlite3
import json
import os
import re
from pathlib import Path
from time import time

def _db():
    root = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "BRAINNET"
    root.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(root / "workspace_chats.sqlite3", timeout=5)
    con.execute("CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, title TEXT NOT NULL, messages TEXT NOT NULL, updated REAL NOT NULL)")
    return con

def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", value):
        raise ValueError("ID de conversa inválido")
    return value

def save(chat_id, messages):
    _id(chat_id)
    if not isinstance(messages, list) or len(messages) > 10000:
        raise ValueError("Histórico excede o limite de 10.000 mensagens")
    rows = []
    for m in messages:
        if not isinstance(m, dict) or m.get("role") not in ("user", "ai") or not isinstance(m.get("text"), str):
            raise ValueError("Mensagem inválida")
        if len(m["text"]) > 500000:
            raise ValueError("Mensagem excede o limite do arquivo")
        rows.append({k:m[k] for k in ("id","role","text","durationMs","timestamp","taskId","resultStatus") if k in m})
    raw = json.dumps(rows, ensure_ascii=False)
    if len(raw.encode("utf-8")) > 16*1024*1024:
        raise ValueError("Conversa excede 16 MiB; crie outra")
    title = next((m["text"].strip().replace("\n"," ")[:70] for m in rows if m["role"]=="user" and m["text"].strip()), "Nova conversa")
    with _db() as con:
        con.execute("INSERT INTO chats VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,messages=excluded.messages,updated=excluded.updated", (chat_id,title,raw,time()))
    return {"ok":True,"title":title}

def listing():
    with _db() as con:
        rows=con.execute("SELECT id,title,updated FROM chats ORDER BY updated DESC").fetchall()
    return [{"id":r[0],"title":r[1],"updated":r[2]} for r in rows]

def load(chat_id):
    with _db() as con:
        row=con.execute("SELECT messages FROM chats WHERE id=?", (_id(chat_id),)).fetchone()
    return json.loads(row[0]) if row else []

def history(rows):
    # Bounded context only. Archived messages are data, not current instructions.
    return [{"role":m["role"],"text":m["text"][:3000],"id":str(m.get("id","")),"timestamp":(m.get("timestamp",0)/1000 if isinstance(m.get("timestamp"),(int,float)) and m["timestamp"]>10**11 else 0)} for m in rows[-120:]]
'''

RICH = r'''
import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";

function wikiLinks() {
  return tree => {
    function walk(node) {
      if (!node.children || ["link","code","inlineCode","html"].includes(node.type)) return;
      node.children=node.children.flatMap(child=>{
        if(child.type!=="text"){walk(child);return [child];}
        return child.value.split(/(\[\[[^\[\]\n]{1,160}\]\])/g).filter(Boolean).map(t=>
          t.startsWith("[[") && t.endsWith("]]")
          ? {type:"link",url:"https://brainnet-note.invalid/"+encodeURIComponent(t.slice(2,-2).trim()),children:[{type:"text",value:t.slice(2,-2).trim()}]}
          : {type:"text",value:t});
      });
    }
    walk(tree);
  };
}
export default function RichText({text,kernel,onNote}) {
  const [error,setError]=React.useState("");
  return <div className="bn-rich"><ReactMarkdown skipHtml remarkPlugins={[remarkGfm,remarkBreaks,wikiLinks]}
    components={{a:({href,children})=>{
      let url;
      try {url=new URL(href);} catch {return <span>{children}</span>;}
      if(url.hostname==="brainnet-note.invalid"){
        let title;
        try{title=decodeURIComponent(url.pathname.slice(1));}catch{return <span>{children}</span>;}
        return onNote ? <button type="button" className="bn-link" onClick={()=>onNote(title)}>{children}</button> : <span>{children}</span>;
      }
      if(!["http:","https:"].includes(url.protocol))return <span>{children}</span>;
      return <a href={url.href} onClick={async e=>{e.preventDefault();try{const r=await kernel.call("open_external_url",url.href);setError(r?.ok?"":r?.error||"Não foi possível abrir o link.");}catch{setError("Ponte indisponível.");}}}>{children}</a>;
    },img:({alt})=><span>{alt||"[Imagem externa não carregada]"}</span>}}
    >{String(text||"")}</ReactMarkdown>{error&&<small role="alert">{error}</small>}</div>;
}
'''

CHAT = r'''
import React,{useState,useEffect,useRef,useCallback} from "react";
import {Mic,MicOff,ChevronDown,Plus} from "lucide-react";

const newId=()=>crypto.randomUUID().replaceAll("-","");
export function useChatArchive(kernel,messages,setMessages,pending,executionRef,makeWelcome){
  const [id,setId]=useState(null),[rows,setRows]=useState([]),[error,setError]=useState(""),[busy,setBusy]=useState(true);
  const ready=useRef(false), active=useRef(null), queue=useRef(Promise.resolve());
  const last=useRef(messages);last.current=messages;
  const persist=useCallback((key,data)=>{
    const job=queue.current.catch(()=>{}).then(async()=>{
      const r=await kernel.call("workspace_chat_save",key,data);
      if(r?.ok!==true)throw Error(r?.error||"Falha ao salvar conversa");
      return r;
    });
    queue.current=job;
    return job;
  },[kernel.call]);
  const refresh=useCallback(async()=>{
    const r=await kernel.call("workspace_chat_list");
    if(r?.ok!==true)throw Error(r?.error||"Arquivo indisponível");
    setRows(r.chats);
    return r.chats;
  },[kernel.call]);
  const activate=useCallback(async(key)=>{
    const r=await kernel.call("workspace_chat_activate",key);
    if(r?.ok!==true)throw Error(r?.error||"Não foi possível abrir a conversa");
    active.current=key;setId(key);
    setMessages(r.messages.length?r.messages:[makeWelcome()]);
    try{localStorage.setItem("bn_active_chat",key);}catch{}
    ready.current=true;
  },[kernel.call,setMessages,makeWelcome]);
  useEffect(()=>{
    if(kernel.bridge!=="pywebview"){setBusy(false);return;}
    let cancelled=false;
    (async()=>{try{
      const list=await refresh();
      if(cancelled)return;
      let old;try{old=localStorage.getItem("bn_active_chat");}catch{}
      await activate(list.find(x=>x.id===old)?.id||list[0]?.id||newId());
    }catch(e){if(!cancelled)setError(String(e.message||e));}
    finally{if(!cancelled)setBusy(false);}})();
    return()=>{cancelled=true;ready.current=false;};
  },[kernel.bridge,refresh,activate]);
  useEffect(()=>{
    if(!id||!ready.current||busy||pending)return;
    persist(id,messages).then(refresh).then(()=>setError("")).catch(e=>setError(String(e.message||e)));
  },[id,messages,busy,pending,persist,refresh]);
  const open=useCallback(async key=>{
    if(!ready.current||executionRef.current.processing||executionRef.current.stopping||pending||busy||key===active.current)return;
    ready.current=false;setBusy(true);
    try{
      await persist(active.current,last.current);
      await activate(key);
      await refresh();setError("");
    }catch(e){setError(String(e.message||e));ready.current=true;}
    finally{setBusy(false);}
  },[persist,activate,refresh,pending,busy,executionRef]);
  return {id,rows,error,busy,ready,open,create:()=>open(newId())};
}
export function ChatArchiveMenu({archive,pending}){
 return <div className="bn-archive-menu"><button type="button" disabled={pending||archive.busy||!archive.id} onClick={archive.create}><Plus size={15}/> Nova conversa</button>
 <label>Conversas salvas<select aria-label="Conversas salvas" value={archive.id||""} disabled={pending||archive.busy} onChange={e=>archive.open(e.target.value)}>
 {!archive.rows.some(x=>x.id===archive.id)&&<option value={archive.id||""}>Nova conversa</option>}
 {archive.rows.map(x=><option key={x.id} value={x.id}>{x.title}</option>)}</select></label>
 {archive.error&&<small role="alert">{archive.error}</small>}</div>;
}
export function MicControl({voiceOn,toggleVoice,voiceMode,setVoiceMode}){
 return <div className="bn-mic-control"><button type="button" aria-pressed={voiceOn} title={voiceOn?"Desligar microfone":"Ligar microfone"} onClick={toggleVoice} style={{color:voiceOn?"#50be94":"var(--muted)"}}>{voiceOn?<Mic size={17}/>:<MicOff size={17}/>} {voiceOn?"Mic ligado":"Mic desligado"}</button>
 <details><summary aria-label="Modo do microfone"><ChevronDown size={15}/></summary><div className="bn-chat-pop"><label><input type="radio" checked={voiceMode==="direct"} onChange={()=>setVoiceMode("direct")}/> Direto · interpretar automaticamente</label><label><input type="radio" checked={voiceMode==="review"} onChange={()=>setVoiceMode("review")}/> Revisar e editar antes de enviar</label><small>Comandos não reconhecidos com segurança serão revisados.</small></div></details></div>;
}
export function LiveTask({pending,events,stream}){
 if(!pending)return null;
 const last=events?.[events.length-1];
 const label=last?.kind==="model_selected"?"Modelo em inferência":last?.kind==="task_finished"?"Recebendo resultado":last?.kind==="task_started"?"Processando solicitação":last?.state||"Aguardando resposta do kernel";
 return <div className="bn-live-task" role="status"><span className="bn-live-dot"/>{label}{last?.model?" · "+last.model:""}{stream?.gap?" · fluxo parcial":""}</div>;
}
'''

CSS = r'''
.bn-chat-composer{flex-shrink:0;min-width:0;border:1px solid var(--edge);border-radius:22px;background:var(--chip);padding:10px 12px;margin-top:10px}
.bn-chat-composer form.bn-main-form{display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:transparent!important;border:0!important;margin:0;padding:0!important}
.bn-chat-composer .bn-main-form>input{flex:1 1 100%;min-height:40px;width:100%;user-select:text}
.bn-chat-composer .bn-chat-tools{flex:1 1 auto;min-width:0;padding:0}
.bn-chat-composer .bn-voice{margin-bottom:8px}
.bn-chat-tools .bn-chat-pop{z-index:40;max-width:min(320px,80vw);max-height:55vh;overflow:auto;white-space:normal}
.bn-mic-control{display:flex;align-items:center;gap:2px}.bn-mic-control button{display:flex;align-items:center;gap:5px}.bn-mic-control summary{display:flex;align-items:center}
.bn-archive-menu{display:flex;flex-direction:column;gap:8px}.bn-archive-menu button{display:flex;align-items:center;gap:5px}.bn-archive-menu select{max-width:100%;width:100%}
.bn-chat-composer select{max-width:140px}.bn-chat-composer .bn-archive-menu select{max-width:100%}
.bn-live-task{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--muted);padding:5px 0}.bn-live-dot{width:7px;height:7px;border-radius:100%;background:var(--cyan);flex-shrink:0}
.bn-rich{white-space:normal;overflow-wrap:anywhere;min-width:0;width:100%;user-select:text;line-height:1.65}.bn-rich p{margin:.35em 0 .75em}.bn-rich h1,.bn-rich h2,.bn-rich h3{font-weight:600;margin:1em 0 .4em}.bn-rich h1{font-size:1.55em}.bn-rich h2{font-size:1.3em}.bn-rich h3{font-size:1.12em}.bn-rich ul,.bn-rich ol{padding-left:1.5em;margin:.5em 0}.bn-rich ul{list-style:disc}.bn-rich ol{list-style:decimal}.bn-rich a,.bn-rich .bn-link{color:var(--cyan);text-decoration:underline;cursor:pointer}.bn-rich pre{overflow:auto;background:var(--cell);border:1px solid var(--edge);padding:10px;border-radius:9px;white-space:pre}.bn-rich code{font-family:monospace}.bn-rich table{display:block;overflow:auto;border-collapse:collapse}.bn-rich th,.bn-rich td{border:1px solid var(--edge);padding:6px 10px}.bn-rich blockquote{border-left:3px solid var(--edge);padding-left:12px;color:var(--muted)}
.bn-live-message{flex-shrink:0;max-width:90%;padding:10px 16px;border-radius:16px;background:var(--chip);border:1px solid var(--edge);overflow-wrap:anywhere}
.bn-chat-messages>div{flex-shrink:0}.bn-chat-composer .bn-chat-tools>details{flex-shrink:0}
'''

def once(s,a,b):
    if s.count(a)!=1:raise ValueError("Âncora incompatível: "+a[:150])
    return s.replace(a,b,1)

def patch_kernel(s):
    anchor='    def get_voice_status(self):'
    addition='''    def workspace_chat_list(self):
        import workspace_chat_archive as archive
        try:return {"ok":True,"chats":archive.listing()}
        except Exception as exc:return {"ok":False,"error":str(exc)[:300]}

    def workspace_chat_save(self, chat_id, messages):
        import workspace_chat_archive as archive
        try:return archive.save(chat_id,messages)
        except Exception as exc:return {"ok":False,"error":str(exc)[:300]}

    def workspace_chat_activate(self, chat_id):
        import workspace_chat_archive as archive
        try:
            with self._kernel._runtime_task_lock:
                if self._kernel._runtime_tasks:
                    return {"ok":False,"error":"Há uma tarefa ativa; aguarde ou cancele."}
                rows=archive.load(chat_id)
                self._chat_history=archive.history(rows)
                self._workspace_context_ids=[]
                self._last_motor_direction=None
                self._ui_motor_window=None
            return {"ok":True,"messages":rows}
        except Exception as exc:return {"ok":False,"error":str(exc)[:300]}

    def open_external_url(self, url):
        import webbrowser
        from urllib.parse import urlsplit
        try:
            if not isinstance(url,str) or len(url)>4096 or any(ord(c)<32 for c in url):
                raise ValueError("URL inválida")
            parsed=urlsplit(url)
            if parsed.scheme not in ("http","https") or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Somente links HTTP(S) sem credenciais")
            return {"ok":bool(webbrowser.open(url,new=2))}
        except Exception as exc:return {"ok":False,"error":str(exc)[:300]}

'''
    s=once(s,anchor,addition+anchor)
    a='        return {"route":voice_route(text)}'
    s=once(s,a,'''        from workspace_intent import local_motion
        from intent_grounding import direct_app_request
        try:
            if local_motion(text) is not None or direct_app_request(text) is not None:
                return {"route":"LOCAL_ACTION"}
        except ValueError:
            pass
        return {"route":voice_route(text)}''')
    return s

def patch_shell(s):
    s=once(s,'import "./shell/p48.css";','''import "./shell/p48.css";
import "./shell/p51.css";
import RichText from "./shell/RichText";
import {useChatArchive,ChatArchiveMenu,MicControl,LiveTask} from "./shell/ChatWorkspace";''')
    a=s.index('            <div className="bn-shell-head">')
    b=s.index('\n',a)
    s=s[:a]+s[b:]
    a=s.index('function ChatPanel(');b=s.index('function BrainStage(',a)
    p=s[a:b]
    p=once(p,'voiceStatus, voiceOn, toggleVoice }','voiceStatus, voiceOn, toggleVoice, voiceMode, setVoiceMode, archive }')
    # The pending stream belongs in the scroll area, not in the fixed header.
    a1=p.index('      {pending && <ReasoningPanel');b1=p.index('      <div className="no-scrollbar flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">',a1)
    p=p[:a1]+p[b1:]
    p=once(p,'className="no-scrollbar flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1"','className="bn-chat-messages no-scrollbar flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1"')
    p=once(p,'<div>{m.text}</div>','<RichText text={m.text} kernel={kernel} onNote={title=>onSend("/nota ler "+title)}/>')
    p=once(p,'{m.duration && <span>• {m.duration}s</span>}','{Number.isFinite(m.durationMs) && <span>• {Math.round(m.durationMs)} ms · GUI↔kernel</span>}{m.resultStatus && <span>{m.resultStatus}</span>}')
    p=once(p,"new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })","m.timestamp ? new Date(m.timestamp).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : ''")
    p=once(p,'        <div ref={endRef} />','''        {pending && <div className="bn-live-message"><ReasoningPanel events={reasoningByTask[currentTaskId]} stream={streamByTask[currentTaskId]}/>{streamByTask[currentTaskId]?.content&&<RichText text={streamByTask[currentTaskId].content} kernel={kernel}/>}</div>}
        <div ref={endRef} />''')
    p=once(p,'[messages, pending]);','[messages, pending, streamByTask[currentTaskId]?.content]);')
    a1=p.index('      <VoiceReview draft={voiceDraft');b1=p.index('      <form onSubmit={submit}',a1)
    p=p[:a1]+'''      <div className="bn-chat-composer">
      <LiveTask pending={pending} events={reasoningByTask[currentTaskId]} stream={streamByTask[currentTaskId]}/>
      <VoiceReview draft={voiceDraft ?? null} setDraft={setVoiceDraft} onSend={onSend} pending={pending} status={voiceStatus}/>
'''+p[b1:]
    p=once(p,'className="mt-3 flex items-center gap-2 rounded-full py-1.5 pl-5 pr-1.5"','className="bn-main-form"')
    a1=p.index('        <SearchButton isSearchMode=')
    p=p[:a1]+'''        <div className="bn-chat-tools">
          <details><summary>☰ Menu</summary><div className="bn-chat-pop"><CopyButton text={historyText} label="Copiar chat inteiro"/><ChatArchiveMenu archive={archive} pending={pending}/><button type="button" disabled={pending} onClick={()=>onSend('/checkup')}>Diagnóstico</button></div></details>
          <select aria-label="Profundidade" title={effortError || "Profundidade de raciocínio"} value={effortMode || ""} disabled={pending} onChange={e=>changeEffort(e.target.value)}><option value="" disabled>Indisponível</option>{['FAST','BALANCED','DEEP','AUTO'].map(mode=><option key={mode} value={mode}>{mode==="DEEP"?"DeepThink":mode}</option>)}</select>
          <MicControl voiceOn={voiceOn} toggleVoice={toggleVoice} voiceMode={voiceMode} setVoiceMode={setVoiceMode}/>
        </div>
'''+p[a1:]
    p=once(p,'      </form>\n    </Bubble>','      </form>\n      </div>\n    </Bubble>')
    # No animated hover scaling or layout transitions in scrollable messages.
    p=once(p,'<motion.div key={m.id} layout initial={{ opacity: 0, y: 16, scale: 0.92 }} animate={{ opacity: 1, y: 0, scale: 1 }}','<motion.div key={m.id} initial={false}')
    p=once(p,'<motion.div key="typing" layout initial=', '<motion.div key="typing" initial=')
    p=once(p,'behavior: "smooth", block: "end"','behavior: "auto", block: "end"')
    p=once(p,'whileHover={{ scale: 1.025, y: -2 }}','')
    s=s[:a]+p+s[b:]
    s=once(s,'  const [voiceDraft, setVoiceDraft] = useState(null);','''  const [voiceDraft, setVoiceDraft] = useState(null);
  const [voiceMode,setVoiceMode] = useState(()=>readLS("bn_voice_mode","review")==="direct"?"direct":"review");
  useEffect(()=>{try{localStorage.setItem("bn_voice_mode",voiceMode);}catch{}},[voiceMode]);''')
    s=once(s,'  const executionRef = useRef({ id: 0, processing: false, stopping: false });','''  const executionRef = useRef({ id: 0, processing: false, stopping: false });
  const makeWelcome=useCallback(()=>({id:crypto.randomUUID(),role:"ai",text:"BRAINNET pronta.",timestamp:Date.now()}),[]);
  const archive=useChatArchive(kernel,messages,setMessages,pending,executionRef,makeWelcome);''')
    # The chat context is supplied by the existing provider below.
    # Context provider has a distinct anchor.
    a1='lite: lite || widgetMode, stopExecution, isStopping, voiceDraft, setVoiceDraft, voiceStatus, voiceOn, toggleVoice'
    if a1+', voiceMode' not in s:s=once(s,a1,a1+', voiceMode, setVoiceMode, archive')
    s=once(s,'{ id: uid(), ...m }','{ id: crypto.randomUUID(), timestamp:Date.now(), ...m }')
    s=once(s,'    if (executionRef.current.processing || executionRef.current.stopping) return;\n    const request = ++executionRef.current.id;','    if (!archive.ready.current || executionRef.current.processing || executionRef.current.stopping) return;\n    const request = ++executionRef.current.id;')
    s=once(s,'taskId: res?.task_budget?.task_id });','taskId: res?.task_budget?.task_id, durationMs:roundtripMs, resultStatus:res.status });')
    s=once(s,'    executionRef.current.processing = true;', '    executionRef.current.processing = true;\n    activeTask.current=null;setTaskTelemetry(null);')
    s=once(s,'  }, [kernel.call, pushLog, pushMessage]);\n\n  useEffect(() => {\n    const selectNote','  }, [kernel.call, pushLog, pushMessage, archive.ready]);\n\n  useEffect(() => {\n    const selectNote')
    s=once(s,'    if (voiceDraft === null || pending) return;','    if (voiceDraft === null || pending || !archive.ready.current) return;')
    s=once(s,'    if (voiceAutoCandidate.current !== voiceDraft) return;','    if (voiceMode !== "direct" || voiceAutoCandidate.current !== voiceDraft) return;')
    s=once(s,'result?.route!=="CHAT")return;','!["CHAT","LOCAL_ACTION"].includes(result?.route))return;')
    s=once(s,"      sendCommand('/voz responder '+voiceDraft);","      sendCommand(result.route==='CHAT'?'/voz responder '+voiceDraft:voiceDraft);")
    s=once(s,'  }, [voiceDraft,pending,kernel.call,sendCommand]);','  }, [voiceDraft,pending,kernel.call,sendCommand,voiceMode,archive.busy]);')
    return s

def patch_notes(s):
    s=once(s,"import React, {useEffect,useRef,useState} from 'react';","import React, {useEffect,useRef,useState} from 'react';\nimport RichText from './RichText';")
    s=once(s,'function load(n){setPreview(false);','function load(n){setPreview(!!n.id);')
    s=once(s,'<MarkdownPreview body={body} links={note.links} onOpen={open}/>','<article className="bn-preview"><RichText text={body} kernel={kernel} onNote={name=>{const link=note.links.find(l=>l.title.toLowerCase()===name.toLowerCase());if(link?.id)open(link.id);else setStatus("Nota referenciada não encontrada.");}}/></article>')
    return s

TESTS = r'''
import pytest
import workspace_chat_archive as archive

@pytest.fixture(autouse=True)
def isolated_db(monkeypatch,tmp_path):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path))

def test_roundtrip_and_isolation():
    a=[{"id":"a","role":"user","text":"Olá","timestamp":1},{"id":"b","role":"ai","text":"Olá 1","durationMs":123}]
    assert archive.save("chat_a",a)["ok"]
    assert archive.save("chat_b",[{"role":"user","text":"Outro"}])["ok"]
    assert archive.load("chat_a")==a
    assert archive.load("chat_b")[0]["text"]=="Outro"
    assert len(archive.listing())==2
    assert archive.load("new_chat")==[]

def test_update_without_duplicate_chat():
    archive.save("chat",[{"role":"user","text":"primeiro"}])
    archive.save("chat",[{"role":"user","text":"primeiro"},{"role":"ai","text":"segundo"}])
    assert len(archive.listing())==1
    assert len(archive.load("chat"))==2

def test_validation_preserves_saved_chat():
    archive.save("valid",[{"role":"user","text":"original"}])
    with pytest.raises(ValueError):
        archive.save("valid",[{"role":"system","text":"invalid"}])
    assert archive.load("valid")[0]["text"]=="original"
    with pytest.raises(ValueError):
        archive.load("../invalid")

def test_context_is_bounded():
    rows=[{"role":"user","text":"x"*4000} for _ in range(130)]
    assert len(archive.history(rows))==120
    assert len(archive.history(rows)[0]["text"])==3000
'''

def main():
    p=argparse.ArgumentParser();p.add_argument("--root",default=r"A:\BRAINNET");p.add_argument("--apply",action="store_true");args=p.parse_args()
    root=Path(args.root).resolve();brain=root/"BRAIN";project=root/"INTERFACE DE USUARIO/BRAINDET IU/project";comp=project/"src/components";shell=comp/"shell"
    kernel=brain/"BRAINNET.py";master=comp/"MasterShell_(1).jsx";notes=shell/"WorkspaceNotes.jsx"
    read=lambda x:x.read_text(encoding="utf-8-sig")
    if not (brain/"test_workspace_p49.py").is_file():raise SystemExit("Instale P49 antes de P51.1.")
    if 'import "./shell/p51.css";' in read(master):
        if all(x.is_file() for x in (brain/"workspace_chat_archive.py",shell/"RichText.jsx",shell/"ChatWorkspace.jsx",shell/"p51.css",brain/"test_workspace_p51.py")):
            print("P51.1 já instalada. Execute os testes e o build.");return
        raise SystemExit("P51.1 incompleta; restaure backup.")
    files={kernel:patch_kernel(read(kernel)),master:patch_shell(read(master)),notes:patch_notes(read(notes)),brain/"workspace_chat_archive.py":ARCHIVE,shell/"RichText.jsx":RICH,shell/"ChatWorkspace.jsx":CHAT,shell/"p51.css":CSS,brain/"test_workspace_p51.py":TESTS}
    old={x:x.read_bytes() if x.exists() else None for x in files}
    for x,c in files.items():
        if x.suffix==".py":compile(c,str(x),"exec")
        if x not in (kernel,master,notes) and x.exists():raise ValueError("Arquivo novo já existe: "+str(x))
        print("PREPARADO:",x.relative_to(root))
    if not args.apply:print("Prévia somente.");return
    package=json.loads(read(project/"package.json"))
    deps={**package.get("dependencies",{}),**package.get("devDependencies",{})}
    missing=[n for n in ("react-markdown","remark-gfm","remark-breaks") if n not in deps or not (project/"node_modules"/n).is_dir()]
    if missing:raise SystemExit("Instale as dependências no projeto React: npm install react-markdown@10 remark-gfm@4 remark-breaks@4")
    backup=root.parent/"BRAINNET_BACKUPS"/("P51_1_"+datetime.now().strftime("%Y%m%d_%H%M%S_%f"));backup.mkdir(parents=True)
    for x,data in old.items():
        if data is not None:
            dest=backup/x.relative_to(root);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    (backup/"manifest.json").write_text(json.dumps([{"path":str(x.relative_to(root)),"existed":v is not None} for x,v in old.items()],indent=2),encoding="utf-8")
    written=[]
    try:
        for x,c in files.items():
            if (x.read_bytes() if x.exists() else None)!=old[x]:raise RuntimeError("Arquivo mudou durante instalação: "+str(x))
            tmp=x.with_name(x.name+".p51tmp")
            if tmp.exists():raise RuntimeError("Temporário existente: "+str(tmp))
            tmp.write_bytes(c.encode("utf-8"));tmp.replace(x);written.append(x)
        python=root/"VENV/Scripts/python.exe"
        subprocess.run([str(python),"-B","-m","pytest","-p","no:cacheprovider","-q","test_workspace_p47.py","test_workspace_p48.py","test_workspace_p49.py","test_workspace_p51.py"],cwd=brain,check=True)
        subprocess.run(["npm.cmd","run","build"],cwd=project,check=True)
    except BaseException:
        for x in reversed(written):
            if old[x] is None:x.unlink(missing_ok=True)
            else:x.write_bytes(old[x])
        print("Falha: código restaurado. Backup:",backup)
        raise
    print("P51.1 instalada. Backup:",backup)

if __name__=="__main__":main()
