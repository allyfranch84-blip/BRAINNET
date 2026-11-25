
import React from "react";
import {THEME_NAMES} from "./themes";

export default function ThemePicker({theme, onToggle}) {
  return (
    <select
      aria-label="Tema da interface"
      value={theme}
      onChange={e => onToggle(e.target.value)}
      className="rounded-lg px-2 py-2 text-xs outline-none"
      style={{
        background:"var(--cell)",
        color:"var(--text)",
        border:"1px solid var(--edge)"
      }}
    >
      {Object.entries(THEME_NAMES).map(([key, name]) => (
        <option key={key} value={key}>{name}</option>
      ))}
    </select>
  );
}
