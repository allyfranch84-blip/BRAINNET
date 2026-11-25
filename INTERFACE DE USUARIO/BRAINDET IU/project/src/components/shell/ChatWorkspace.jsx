
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
