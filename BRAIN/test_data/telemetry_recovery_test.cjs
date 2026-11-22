const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
const ui = process.argv[2];
const req = createRequire(path.join(ui, "package.json"));
function load(name, requireFn) {
  const code = req("esbuild").transformSync(fs.readFileSync(path.join(ui, "src/components", name), "utf8"), { loader: name.endsWith("jsx") ? "jsx" : "js", format: "cjs" }).code;
  const module = { exports: {} };
  new Function("require", "module", "exports", code)(requireFn, module, module.exports);
  return module.exports.default;
}
const flush = async () => { for (let n = 0; n < 12; n++) await Promise.resolve(); };
async function main() {
  let effect, cleanup, snapshot, calls = 0, id = 0;
  const intervals = new Map(), timers = new Map(), listeners = {};
  global.window = { addEventListener: (name, fn) => { listeners[name] = fn; }, removeEventListener: (name) => { delete listeners[name]; } };
  global.document = { hidden: false, addEventListener: (name, fn) => { listeners[name] = fn; }, removeEventListener: (name) => { delete listeners[name]; } };
  const old = { setInterval, clearInterval, setTimeout, clearTimeout };
  global.setInterval = (fn, delay) => { assert.equal(delay, 3000); intervals.set(++id, fn); return id; };
  global.clearInterval = (key) => intervals.delete(key);
  global.setTimeout = (fn) => { timers.set(++id, fn); return id; };
  global.clearTimeout = (key) => timers.delete(key);
  try {
    const hook = load("useKernelTelemetry.js", (name) => name === "react" ? { useEffect: (fn) => { effect = fn; }, useState: (initial) => { snapshot = initial; return [initial, (value) => { snapshot = value; }]; } } : req(name));
    hook("get_diagnostics"); cleanup = effect();
    assert.equal(snapshot.connection, "waiting");
    let answer = null;
    window.pywebview = { api: { get_diagnostics: () => { calls++; return answer; } } };
    listeners.pywebviewready(); await flush();
    assert.equal(snapshot.connection, "unavailable");
    const tick = () => [...intervals.values()][0]();
    answer = undefined; tick(); await flush();
    assert.equal(snapshot.data, null);
    answer = { ollama: { ok: true } }; tick(); await flush();
    assert.equal(snapshot.connection, "connected");
    let resolveOld;
    answer = new Promise((resolve) => { resolveOld = resolve; });
    tick(); await flush();
    const count = calls;
    tick(); await flush(); assert.equal(calls, count);
    [...timers.values()].forEach((fn) => fn());
    answer = { ollama: { ok: false } }; tick(); await flush();
    assert.equal(snapshot.data.ollama.ok, false);
    resolveOld({ ollama: { ok: true } }); await flush();
    assert.equal(snapshot.data.ollama.ok, false);
    document.hidden = true; const hiddenCount = calls; tick(); await flush();
    assert.equal(calls, hiddenCount);
    cleanup(); assert.equal(intervals.size, 0); assert.equal(timers.size, 0);
  } finally {
    Object.assign(global, old);
  }
  const React = req("react"), server = req("react-dom/server");
  const Integration = load("IntegrationStatus.jsx", (name) => name === "./useKernelTelemetry" ? () => ({ data: null, connection: "connected" }) : req(name));
  const World = load("WorldModelWidget.jsx", (name) => name === "./useKernelTelemetry" ? () => ({ data: undefined, connection: "connected" }) : name === "./IntegrationStatus" ? Integration : req(name));
  const html = server.renderToStaticMarkup(React.createElement(World));
  assert.ok(html.includes("--"));
  assert.equal(html.includes("undefined"), false);
  assert.equal(html.includes("NaN"), false);
  assert.equal(html.includes("Não treinado"), false);
  const Gauge = () => React.createElement("span", null, "Metacognição");
  const Dashboard = load("TelemetryDashboard.jsx", (name) => name === "./WorldModelWidget" ? World : name === "./MetacognitionGauge" ? Gauge : req(name));
  const dashboardHtml = server.renderToStaticMarkup(React.createElement(Dashboard));
  assert.ok(dashboardHtml.includes("Painel de Telemetria"));
  assert.ok(dashboardHtml.includes("Nenhum dado de telemetria disponível."));
  const shell = fs.readFileSync(path.join(ui, "src/components/MasterShell_(1).jsx"), "utf8");
  const menuSource = shell.match(/function Menu\([\s\S]*?\n\}/)[0];
  const setup = `const React=require("react"); const {useState}=React; const motion=new Proxy({}, {get:()=>"motion-node"});
    const AnimatePresence="presence", Bubble="bubble", Orb="orb", MenuItem="menu-item", SectionLabel="label", VoiceControl="voice", Icon="icon";
    const SPRING={}, JELLY={}, MONO={}, DISPLAY="sans-serif";`;
  const menuJS = req("esbuild").transformSync(setup + menuSource + ";module.exports=Menu;", {loader:"jsx",format:"cjs"}).code;
  const menuModule = {exports:{}};
  new Function("require","module","exports",menuJS)((name)=>name === "react" ? {...React,useState:(v)=>[v,()=>{}]}:req(name),menuModule,menuModule.exports);
  let navigated = null;
  const tree = menuModule.exports({expanded:true, skills:[], view:"home", groups:{loose:[],folders:[]}, voice:{}, onNavigate:(v)=>{navigated=v;}});
  function findTelemetry(node) {
    if (!node || typeof node !== "object") return null;
    if (node.props?.label === "Telemetria") return node;
    for (const child of React.Children.toArray(node.props?.children)) { const result=findTelemetry(child); if(result)return result; }
    return null;
  }
  const menuItem = findTelemetry(tree);
  assert.ok(menuItem);
  menuItem.props.onClick();
  assert.equal(navigated,"telemetry");
  assert.ok(shell.includes('v === "telemetry" ? ('));
  assert.ok(shell.includes('<TelemetryDashboard />'));
  assert.ok(shell.includes('view === "telemetry" || view === "schema"'));
  const themeBody = shell.match(/\/\/ Consulta o tema[^\n]*\n  useEffect\(\(\) => \{([\s\S]*?)\n  \}, \[\]\);/)[1];
  const themeListeners = {};
  let theme = null, themeCalls = 0;
  const themeWindow = {addEventListener:(key,fn)=>{themeListeners[key]=fn;},removeEventListener:(key)=>{delete themeListeners[key];}};
  const disposeTheme = new Function("window","document","setTheme",themeBody)(themeWindow,{documentElement:{setAttribute:()=>{}}},(value)=>{theme=value;});
  await flush(); assert.equal(theme,null);
  themeWindow.pywebview={api:{get_theme:async()=>{themeCalls++;return "light";}}};
  await themeListeners.pywebviewready(); await flush();
  assert.equal(theme,"light");
  await themeListeners.pywebviewready(); assert.equal(themeCalls,1);
  disposeTheme(); assert.equal(themeListeners.pywebviewready,undefined);
  const integration = fs.readFileSync(path.join(ui, "src/components/IntegrationStatus.jsx"), "utf8");
  assert.ok(integration.includes('useKernelTelemetry("get_diagnostics", 3000)'));
  assert.ok(integration.includes('useKernelTelemetry("get_usage_report", 3000)'));
  console.log("Telemetry recovery OK");
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
