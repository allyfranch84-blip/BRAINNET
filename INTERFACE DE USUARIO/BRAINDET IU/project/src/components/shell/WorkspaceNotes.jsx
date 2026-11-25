import React, {useEffect,useRef,useState} from 'react';
import RichText from './RichText';

const field='bn-field';
function MarkdownPreview({body,links,onOpen}) {
  const inline=text=>text.split(/(\[\[[^\[\]\n]+\]\]|\*\*[^*]+\*\*)/g).map((part,i)=>{
    if(part.startsWith('[[')&&part.endsWith(']]')){const name=part.slice(2,-2).trim();const link=links.find(l=>l.title.trim().toLowerCase()===name.toLowerCase());return <button key={i} disabled={!link?.id} onClick={()=>onOpen(link.id)}>{name}</button>;}
    if(part.startsWith('**')&&part.endsWith('**'))return <strong key={i}>{part.slice(2,-2)}</strong>;
    return <React.Fragment key={i}>{part}</React.Fragment>;
  });
  const nodes=[];let code=null;
  body.split('\n').forEach((line,i)=>{if(line.startsWith('```')){if(code===null)code=[];else{nodes.push(<pre key={i}>{code.join('\n')}</pre>);code=null;}return;}if(code!==null){code.push(line);return;}const heading=line.match(/^(#{1,6})\s+(.+)/);if(heading){const Tag='h'+heading[1].length;nodes.push(<Tag key={i}>{inline(heading[2])}</Tag>);}else nodes.push(<p key={i}>{inline(line.replace(/^[-*]\s+/,'• '))}</p>);});
  if(code!==null)nodes.push(<pre key="unfinished">{code.join('\n')}</pre>);
  return <article className="bn-preview">{nodes}</article>;
}
export default function WorkspaceNotes({kernel}) {
  const [rows,setRows]=useState([]),[query,setQuery]=useState(''),[note,setNote]=useState(null);
  const [title,setTitle]=useState(''),[body,setBody]=useState(''),[status,setStatus]=useState(''),[busy,setBusy]=useState(false);
  const [preview,setPreview]=useState(false);
  const [linkTitle,setLinkTitle]=useState('');
  const serial=useRef(false), searchSerial=useRef(0);
  const dirty=note!==null&&(title!==note.title||body!==note.body||!note.id);
  async function refresh(q=query){
    const id=++searchSerial.current;
    const r=await kernel.call('workspace_notes_list',q);
    if(id!==searchSerial.current)return;
    if(r?.ok===true)setRows(r.notes); else setStatus(r?.error||'Banco indisponível');
  }
  useEffect(()=>{const id=setTimeout(()=>refresh(query),180);return()=>{clearTimeout(id);++searchSerial.current;};},[query,kernel.call]);
  useEffect(()=>{const reload=()=>refresh(query);window.addEventListener("aios:notes_changed",reload);return()=>window.removeEventListener("aios:notes_changed",reload);},[query,kernel.call]);
  function load(n){setPreview(!!n.id);setNote(n);setTitle(n.title);setBody(n.body);}
  async function open(id){
    if(serial.current)return;
    if(dirty){setStatus('Salve ou descarte a edição antes de trocar de nota.');return;}
    serial.current=true;setBusy(true);
    try{const r=await kernel.call('workspace_note_get',id);if(r?.ok===true){load(r.note);setStatus('');}else setStatus(r?.error||'Nota indisponível');}finally{serial.current=false;setBusy(false);}
  }
  function create(){if(serial.current)return;if(dirty){setStatus('Salve ou descarte a edição atual.');return;}load({id:null,title:'',body:'',revision:0,links:[],backlinks:[]});setStatus('Nova nota ainda não salva');}
  async function save(){if(serial.current||!note)return;serial.current=true;setBusy(true);
    try{const r=await kernel.call('workspace_note_save',note.id,title,body,note.revision);if(r?.ok===true){load(r.note);setStatus('Salva no banco local');await refresh();}else setStatus(r?.error||'Não foi possível salvar');}finally{serial.current=false;setBusy(false);}}
  useEffect(()=>{if(!dirty)return;const warn=e=>{e.preventDefault();e.returnValue='';};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);},[dirty]);
  return <div className="bn-notes" aria-label="Notas locais">
    <aside><h2>Notas</h2><button onClick={create} disabled={busy}>+ Nova nota</button><input className={field} value={query} maxLength={200} onChange={e=>setQuery(e.target.value)} placeholder="Buscar título ou conteúdo" aria-label="Buscar notas"/>
      {rows.map(r=><button key={r.id} aria-current={note?.id===r.id} disabled={busy} onClick={()=>open(r.id)}>{r.title}</button>)}
    </aside>
    <section><p role="status">{status}{dirty?' · alterações não salvas':''}</p>
      {note?<><input className={field} value={title} maxLength={160} disabled={busy} onChange={e=>setTitle(e.target.value)} placeholder="Título da nota" aria-label="Título da nota"/>
      <div className="bn-actions"><button onClick={()=>setPreview(v=>!v)}>{preview?"Editar":"Visualizar Markdown"}</button><button onClick={save} disabled={busy||!title.trim()||!dirty}>Salvar</button><button disabled={busy||!dirty} onClick={()=>{if(note.id)load(note);else{setNote(null);setTitle('');setBody('');}setStatus('Edição descartada');}}>Descartar edição</button></div>
      {preview?<article className="bn-preview"><RichText text={body} kernel={kernel} onNote={name=>{const link=note.links.find(l=>l.title.toLowerCase()===name.toLowerCase());if(link?.id)open(link.id);else setStatus("Nota referenciada não encontrada.");}}/></article>:<textarea className={field} value={body} maxLength={200000} disabled={busy} onChange={e=>setBody(e.target.value)} placeholder="Markdown e links [[Outra nota]]" aria-label="Conteúdo da nota"/>}
      <div className="bn-actions"><select className="bn-field" aria-label="Nota para vincular" value={linkTitle} onChange={e=>setLinkTitle(e.target.value)}><option value="">Escolher nota para vincular</option>{rows.filter(r=>r.id!==note.id).map(r=><option key={r.id} value={r.title}>{r.title}</option>)}</select><button disabled={busy||!linkTitle} onClick={()=>{setBody(b=>b+"\n[["+linkTitle+"]]\n");setLinkTitle("");setPreview(false);}}>Inserir link</button><button disabled={!note.id||dirty||busy} onClick={()=>{window.dispatchEvent(new CustomEvent("aios:note_context",{detail:{title:note.title}}));}}>Usar no chat</button></div>
      <small>Os links são atualizados ao salvar. Prévia Markdown básica: títulos, negrito, listas, código e links.</small>
      <h3>Links</h3><div className="bn-actions">{note.links.map((l,i)=><button key={i} disabled={!l.id||busy} onClick={()=>open(l.id)}>{l.title}{!l.id?' (não criada)':''}</button>)}</div>
      <h3>Referências a esta nota</h3><div className="bn-actions">{note.backlinks.map(l=><button key={l.id} disabled={busy} onClick={()=>open(l.id)}>{l.title}</button>)}</div></>:<p>Selecione uma nota ou crie uma nova. Nenhum modelo é necessário.</p>}
    </section></div>;
}
