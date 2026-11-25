
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
