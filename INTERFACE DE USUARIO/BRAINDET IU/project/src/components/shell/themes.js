const BASE_THEMES = {
  dark: {
    "--glass": "rgba(18,16,28,.38)", "--cell": "rgba(30,26,44,.85)", "--edge": "rgba(255,255,255,.10)",
    "--spec": "rgba(255,255,255,.22)", "--shadow": "rgba(0,0,0,.65)", "--glow": "rgba(140,230,255,.32)",
    "--cyan": "#7ff0e0", "--violet": "#d29bff", "--warm": "#ffb27a", "--rose": "#ff8fc0", "--rim": "#7ff0e0",
    "--text": "#f1f2ff", "--muted": "rgba(224,226,245,.56)", "--bubble-user": "rgba(210,155,255,.18)",
    "--chip": "rgba(255,255,255,.06)", "--err": "#ff6f8e", "--bg-a": "#0d0d14", "--bg-b": "#020204",
    "--smoke": "236,240,255", "--dots": "236,240,255",
  },
  light: {
    "--glass": "rgba(255,255,255,.34)", "--cell": "rgba(255,255,255,.88)", "--edge": "rgba(255,255,255,.75)",
    "--spec": "rgba(255,255,255,.95)", "--shadow": "rgba(50,56,70,.22)", "--glow": "rgba(60,230,140,.38)",
    "--cyan": "#0b9d6a", "--violet": "#7a5ce0", "--warm": "#e0803a", "--rose": "#d6508e", "--rim": "#2fe07a",
    "--text": "#14151b", "--muted": "rgba(20,21,27,.55)", "--bubble-user": "rgba(47,224,122,.18)",
    "--chip": "rgba(20,21,27,.05)", "--err": "#d63a5a", "--bg-a": "#eceef0", "--bg-b": "#c3c6cd",
    "--smoke": "14,14,20", "--dots": "20,22,34",
  },
};

function palette(base, values) {
  return Object.freeze({...BASE_THEMES[base], ...values});
}

export const THEMES = Object.freeze({
  dark: BASE_THEMES.dark,
  light: BASE_THEMES.light,

  graphite: palette("dark", {
    "--bg-a":"#161616", "--bg-b":"#0b0b0b",
    "--glass":"#202020", "--cell":"#282828",
    "--cyan":"#b8c0cc", "--violet":"#d4d4d8",
    "--rim":"#9299a3", "--text":"#f4f4f5",
    "--muted":"#a1a1aa", "--bubble-user":"#363636",
    "--glow":"rgba(180,190,200,.12)"
  }),

  midnight: palette("dark", {
    "--bg-a":"#101e32", "--bg-b":"#07101d",
    "--glass":"#122339", "--cell":"#192c44",
    "--cyan":"#60a5fa", "--violet":"#a5b4fc",
    "--rim":"#60a5fa", "--text":"#e2ebff",
    "--muted":"#a7b8d2", "--bubble-user":"#263c61",
    "--glow":"rgba(96,165,250,.15)"
  }),

  forest: palette("dark", {
    "--bg-a":"#10241a", "--bg-b":"#07100c",
    "--glass":"#172b20", "--cell":"#20382b",
    "--cyan":"#6ee7a0", "--violet":"#a3e635",
    "--rim":"#6ee7a0", "--text":"#e1f5e8",
    "--muted":"#a7c9b2", "--bubble-user":"#284a35",
    "--glow":"rgba(110,231,160,.12)"
  }),

  paper: palette("light", {
    "--bg-a":"#f7f7f5", "--bg-b":"#e8e8e5",
    "--glass":"#ffffff", "--cell":"#ffffff",
    "--cyan":"#2458b5", "--violet":"#475569",
    "--rim":"#94a3b8", "--text":"#232323",
    "--muted":"#626975", "--bubble-user":"#e1eafa",
    "--edge":"#d8dde4", "--glow":"rgba(37,99,235,.10)"
  }),

  lavender: palette("light", {
    "--bg-a":"#eeeaf6", "--bg-b":"#ded6ed",
    "--glass":"#faf8ff", "--cell":"#ffffff",
    "--cyan":"#6544a0", "--violet":"#a04478",
    "--rim":"#9676bf", "--text":"#302540",
    "--muted":"#685d79", "--bubble-user":"#e8dff5",
    "--edge":"#d5c9e5", "--glow":"rgba(118,82,181,.12)"
  })
});

export const THEME_NAMES = Object.freeze({
  dark:"Neural",
  graphite:"Graphite",
  midnight:"Midnight",
  forest:"Forest",
  light:"Claro original",
  paper:"Paper",
  lavender:"Lavender"
});

export function validTheme(value) {
  return Object.hasOwn(THEMES, value) ? value : "dark";
}

export function isLightTheme(value) {
  return ["light", "paper", "lavender"].includes(value);
}
