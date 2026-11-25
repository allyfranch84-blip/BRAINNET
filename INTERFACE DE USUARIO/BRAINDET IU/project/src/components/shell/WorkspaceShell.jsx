import React from 'react';
import ThemePicker from './ThemePicker';
import {Home,MessageSquare,NotebookPen,Network,Activity,Workflow,Terminal,Mic,MicOff,Menu} from 'lucide-react';
const navIcons={home:Home,chat:MessageSquare,notes:NotebookPen,semantic:Network,telemetry:Activity,automations:Workflow};

export const WORKSPACE_LABELS={home:'Início',chat:'Conversa',notes:'Notas',semantic:'Rede semântica',telemetry:'Telemetria',automations:'Automações',schema:'Painel'};
const names=(id,skills=[])=>WORKSPACE_LABELS[id]||skills.find(s=>s.id===id)?.name||id;
export function WorkspaceSidebar({expanded,onToggle,view,onNavigate,skills,voice,consoleOpen,onToggleConsole}){
  const item=id=>{const Icon=navIcons[id]||Workflow;return <button key={id} title={names(id,skills)} aria-current={view===id?'page':undefined} onClick={()=>onNavigate(id)}><Icon size={17}/>{expanded&&<span>{names(id,skills)}</span>}</button>;};
  return <aside className="bn-side" style={{width:expanded?205:62}}><button onClick={onToggle} aria-expanded={expanded} aria-label="Menu"><Menu size={18}/>{expanded&&<span>BRAINNET</span>}</button>
    <details open><summary>{expanded?'Workspace':'W'}</summary>{['home','chat','notes'].map(item)}</details>
    <details><summary>{expanded?'Cognição':'C'}</summary>{['semantic'].map(item)}</details>
    <details><summary>{expanded?'Sistema':'S'}</summary>{item('telemetry')}<button aria-pressed={consoleOpen} onClick={onToggleConsole}><Terminal size={16}/>{expanded&&'Logs'}</button></details>
    <details><summary>{expanded?'Habilidades':'H'}</summary>{item('automations')}{skills.filter(s=>!['automations','web_search'].includes(s.id)).map(s=>item(s.id))}</details>
    <div style={{marginTop:'auto'}}><button disabled={voice.busy} aria-pressed={voice.active} onClick={voice.onToggle}>{voice.active?<Mic size={17}/>:<MicOff size={17}/>} {expanded&&(voice.active?'Desligar mic':'Ligar mic')}</button></div>
  </aside>;
}
export function WorkspaceTabs({tabs,view,onNavigate,onClose,skills}){
 return <nav className="bn-tabs" aria-label="Abas do workspace">{tabs.map(id=><div key={id} className="bn-tab" data-active={view===id}><button onClick={()=>onNavigate(id)} aria-current={view===id?'page':undefined}>{names(id,skills)}</button>{id!=='home'&&<button aria-label={'Fechar '+names(id,skills)} onClick={()=>onClose(id)}>×</button>}</div>)}</nav>;
}
export function WorkspaceHome({theme,onToggleTheme,lite,setLite,onNavigate,showPointers,setShowPointers,kernel,onToggleWidget}){
 return <div className="bn-home"><h1>BRAINNET</h1><p>Workspace cognitivo local</p><section><h2>Trabalho</h2><div className="bn-actions"><button onClick={()=>onNavigate('chat')}>Conversa</button><button onClick={()=>onNavigate('notes')}>Notas</button><button onClick={()=>onNavigate('telemetry')}>Telemetria</button></div></section>
 <section><h2>Aparência</h2><label>Tema <ThemePicker theme={theme} onToggle={onToggleTheme}/></label><label><input type="checkbox" checked={lite} onChange={e=>setLite(e.target.checked)}/> Modo leve</label><label><input type="checkbox" checked={showPointers} onChange={e=>setShowPointers(e.target.checked)}/> Mostrar ações de ponteiro pendentes</label><button onClick={onToggleWidget} disabled={kernel.bridge!=='pywebview'}>Abrir Hotbar</button></section></div>;
}
export function CognitiveStatus({type,task,conversationStatus,skills}){
 if(type==='automations')return <div className="bn-home"><h2>Automações</h2><p>{skills.length?'Habilidades listadas pelo kernel não comprovam uma rotina agendada.':'Nenhuma habilidade anunciada pelo kernel.'}</p><p>Nenhuma rotina com contrato de automação verificável está disponível neste painel. Não são simuladas execuções.</p></div>;
 if(type==='semantic')return <div className="bn-home"><h2>Rede semântica</h2><p>Conceitos, relações e habilidades generalizáveis. A ponte de treinamento não está disponível nesta versão. Notas são independentes da rede semântica.</p></div>;
 return <div className="bn-home"><h2>Estado cognitivo</h2><p>Dados da última tarefa recebida da ponte. Não representa atividade neural.</p><dl><dt>Modelo configurado</dt><dd>{conversationStatus?.model||'Indisponível'} (disponibilidade não verificada)</dd><dt>Última tarefa</dt><dd>{task?.budget?.task_id||'Nenhuma recebida'}</dd><dt>Fase</dt><dd>{task?.phase||'Indisponível'}</dd><dt>Resultado</dt><dd>{task?.result_status||'Não confirmado'}</dd><dt>Habilidades anunciadas</dt><dd>{skills.length}</dd></dl></div>;
}
export function VoiceReview({draft,setDraft,onSend,pending,status}){
 return <>{status?.error&&<p role="status" className="bn-voice">{status.error}</p>}{draft!==null&&<form className="bn-voice" onSubmit={e=>{e.preventDefault();if(!pending&&draft.trim()){onSend(draft.trim());setDraft(null);}}}><label htmlFor="bn-voice-draft">Transcrição de voz · confirme ações ou corrija o pedido.</label><input id="bn-voice-draft" value={draft} onChange={e=>setDraft(e.target.value)} className="bn-field"/><button disabled={pending||!draft.trim()}>Confirmar e enviar</button><button type="button" onClick={()=>setDraft(null)}>Descartar</button></form>}</>;
}
