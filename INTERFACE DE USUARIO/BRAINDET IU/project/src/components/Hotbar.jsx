
import React from "react";
import {Mic, Search, Maximize2, X} from "lucide-react";

function Control({label, icon:Icon, active, onClick}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={typeof onClick !== "function"}
      className="flex items-center justify-center rounded-lg border"
      style={{
        minWidth:38,
        minHeight:38,
        color:active ? "var(--cyan,#7ff0e0)" : "var(--text,#eee)",
        background:"var(--chip,#222)",
        borderColor:"var(--edge,#333)",
        WebkitAppRegion:"no-drag"
      }}
    >
      <Icon size={19}/>
    </button>
  );
}

export default function Hotbar({
  isMicActive=false,
  onMic, onSearch, onExpand, onClose
}) {
  return (
    <div
      className="grid h-full w-full grid-cols-2 gap-2 p-3"
      style={{background:"var(--bg-a,#101010)"}}
    >
      <Control label="Microfone" icon={Mic}
        active={isMicActive} onClick={onMic}/>
      <Control label="Abrir chat para pesquisa" icon={Search}
        onClick={onSearch}/>
      <Control label="Restaurar interface" icon={Maximize2}
        onClick={onExpand}/>
      <Control label="Sair do modo widget" icon={X}
        onClick={onClose}/>
    </div>
  );
}
