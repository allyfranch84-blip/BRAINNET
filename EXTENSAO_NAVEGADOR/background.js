importScripts("background_research.js");
const BRIDGE_URL = "http://127.0.0.1:9876";
let pollingActive = false;

chrome.alarms.create("brainnet_keepalive", { periodInMinutes: 0.4 });
chrome.alarms.onAlarm.addListener(() => {
  if (!pollingActive) startLongPoll();
});

// Função injetada dentro da aba ativa para extrair Texto, Links Categorizados e Caixas de Colisão (Hitboxes)
function domInspectorAndActuator(payload) {
  const mode = payload.mode || "EXTRACT";
  const dpr = window.devicePixelRatio || 1;
  const borderX = Math.max(0, (window.outerWidth - window.innerWidth) / 2);
  const chromeTop = Math.max(0, window.outerHeight - window.innerHeight - borderX);

  function calcHitbox(el) {
    const r = el.getBoundingClientRect();
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    return {
      left: Math.round(r.left),
      top: Math.round(r.top),
      width: Math.round(r.width),
      height: Math.round(r.height),
      client_x: Math.round(cx),
      client_y: Math.round(cy),
      screen_x: Math.round((window.screenX + borderX + cx) * dpr),
      screen_y: Math.round((window.screenY + chromeTop + cy) * dpr)
    };
  }

  function categorizeUrl(url, title) {
    const u = url.toLowerCase();
    const t = title.toLowerCase();
    if (u.includes("youtube.com/watch") || u.includes("vimeo") || t.includes("vídeo")) return "VIDEO";
    if (u.includes("github.com") || u.includes("docs.") || u.includes("stackoverflow")) return "DOCUMENTACAO_CODIGO";
    if (u.includes("wikipedia.org") || t.includes("como fazer") || t.includes("receita") || t.includes("guia")) return "GUIA_CONCEITUAL";
    if (u.includes("g1.globo") || u.includes("noticias") || u.includes("news")) return "NOTICIA";
    return "PAGINA_GERAL";
  }

  // MODO 1: CONTROLE DE VÍDEO / PLAY / PAUSE COM CAIXA DE COLISÃO EXATA
  if (mode === "VIDEO_CONTROL") {
    const action = payload.video_action || "toggle"; // play, pause, toggle
    const video = document.querySelector("video");
    const playBtn = document.querySelector(".ytp-play-button, button[aria-label*='Play' i], button[aria-label*='Pause' i], button[aria-label*='Reproduzir' i], button[aria-label*='Pausar' i]");
    
    let hitbox = null;
    if (playBtn) hitbox = calcHitbox(playBtn);
    else if (video) hitbox = calcHitbox(video);

    if (video) {
      if (action === "play") video.play();
      else if (action === "pause") video.pause();
      else video.paused ? video.play() : video.pause();
      return { ok: true, state: video.paused ? "PAUSED" : "PLAYING", hitbox: hitbox, method: "HTML5_VIDEO_AND_HITBOX" };
    } else if (playBtn) {
      playBtn.click();
      return { ok: true, state: "CLICKED_PLAY_BTN", hitbox: hitbox, method: "DOM_BUTTON_HITBOX" };
    }
    return { ok: false, error: "Nenhum elemento de vídeo encontrado na aba atual." };
  }

  // MODO 2: DIGITAR NA BARRA DE BUSCA INTERNA DA PÁGINA (GOOGLE, YOUTUBE, SITES)
  if (mode === "PAGE_SEARCH") {
    const input = document.querySelector("textarea[name='q'], input[name='q'], input[type='search'], input#search, input[placeholder*='Pesquisar' i], input[placeholder*='Search' i]");
    if (!input) return { ok: false, error: "Campo de busca interno não localizado no DOM." };
    const hb = calcHitbox(input);
    input.focus();
    input.value = payload.query || "";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    const form = input.closest("form");
    if (form) form.submit();
    else input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
    return { ok: true, hitbox: hb, typed: payload.query };
  }

  // MODO 3: CLICAR EM ELEMENTO POR TEXTO OU SELETOR E DEVOLVER CAIXA DE COLISÃO
  if (mode === "CLICK_ELEMENT") {
    const targetText = (payload.target_text || "").toLowerCase();
    const candidates = Array.from(document.querySelectorAll("button, a, [role='button'], input[type='submit']"));
    const found = candidates.find(el => {
      const txt = (el.innerText || el.getAttribute("aria-label") || el.value || "").toLowerCase();
      return txt.includes(targetText) && el.getBoundingClientRect().width > 5;
    });
    if (!found) return { ok: false, error: `Elemento '${payload.target_text}' não achado.` };
    found.scrollIntoView({ block: "center", behavior: "instant" });
    const hb = calcHitbox(found);
    if (!payload.only_coords) found.click();
    return { ok: true, hitbox: hb, text: (found.innerText || "").slice(0, 60) };
  }

  // MODO 4: EXTRAÇÃO PROFUNDA DE CONCEITO DA PÁGINA + LINKS ORDINAIS DE REDIRECIONAMENTO
  const isGoogle = location.hostname.includes("google.");
  let rawLinks = [];

  if (isGoogle) {
    // No Google, captura estritamente resultados orgânicos reais (links com título H3)
    const h3List = Array.from(document.querySelectorAll("#search a h3, #rso a h3"));
    rawLinks = h3List.map(h3 => h3.closest("a")).filter(Boolean);
  } else {
    rawLinks = Array.from(document.querySelectorAll("main a[href], article a[href], #contents a#video-title-link, body a[href]"));
  }

  const seenUrls = new Set();
  const links = [];
  for (const a of rawLinks) {
    const href = a.href || "";
    if (!href.startsWith("http")) continue;
    if (isGoogle && (href.includes("google.com/search") || href.includes("accounts.google") || href.includes("support.google"))) continue;
    if (seenUrls.has(href)) continue;

    const r = a.getBoundingClientRect();
    if (r.width < 15 || r.height < 10) continue;

    const title = (a.querySelector("h3")?.innerText || a.innerText || a.getAttribute("title") || "").replace(/\s+/g, " ").trim();
    if (title.length < 4) continue;

    seenUrls.add(href);
    links.push({
      index: links.length + 1,
      title: title.slice(0, 120),
      url: href,
      category: categorizeUrl(href, title),
      hitbox: calcHitbox(a)
    });
    if (links.length >= 15) break;
  }

  // Extrai o texto conceitual limpo da página (ignorando scripts/menus ocultos)
  const mainNode = document.querySelector("main") || document.querySelector("article") || document.querySelector("#search, #content");
  const blocks = mainNode ? Array.from(mainNode.querySelectorAll("h1, h2, h3, p, li")) : [];
  const textNodes = (blocks.length ? blocks : (mainNode ? [mainNode] : Array.from(document.querySelectorAll("h1, p"))))
    .filter(node => !node.closest("nav, header, footer, aside, [hidden], [aria-hidden='true']"))
    .filter(node => !node.parentElement?.closest("p, li"));
  const limit = Math.min(3000, Math.max(1, Number(payload.max_chars) || 3000));
  const cleanText = (textNodes.length ? textNodes.map(node => {
    const content = node.cloneNode(true);
    content.querySelectorAll("script, style, nav, header, footer, aside, noscript, [hidden], [aria-hidden='true']").forEach(hidden => hidden.remove());
    return content.innerText || content.textContent || "";
  }).join("\n\n") : "")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
    .slice(0, limit);

  return {
    ok: true,
    url: location.href,
    title: document.title,
    is_search_engine: isGoogle,
    text_excerpt: cleanText,
    links_count: links.length,
    links: links
  };
}

async function handleCommand(cmd) {
  try {
    if (!commandIsFresh(cmd)) return {ok:false,error:"Command expired or missing deadline",dispatch_state:"NOT_EXECUTED"};
    if (cmd.action === "RESEARCH_BACKGROUND") return await runBackgroundResearch(cmd, chrome);
    if (cmd.action === "PING") {
      const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      return { ok: true, active_url: tab ? tab.url : "", active_title: tab ? tab.title : "" };
    }

    if (cmd.action === "OPEN_TAB_AND_WAIT") {
      const tab = await chrome.tabs.create({ url: cmd.url, active: true });
      await new Promise(resolve => {
        const listener = (tabId, info) => {
          if (tabId === tab.id && info.status === "complete") {
            chrome.tabs.onUpdated.removeListener(listener);
            setTimeout(resolve, 600);
          }
        };
        chrome.tabs.onUpdated.addListener(listener);
        setTimeout(() => { chrome.tabs.onUpdated.removeListener(listener); resolve(); }, 7000);
      });
      const res = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: domInspectorAndActuator,
        args: [{ mode: "EXTRACT", ...(cmd.extract_options || {}), max_chars: 3000 }]
      });
      const resultObj = res[0]?.result || { ok: false };
      resultObj.tab_id = tab.id;
      return resultObj;
    }

    if (cmd.action === "NAVIGATE_ACTIVE_TAB") {
      const tab = Number.isInteger(cmd.tab_id) ? await chrome.tabs.get(cmd.tab_id)
        : (await chrome.tabs.query({ active: true, lastFocusedWindow: true }))[0];
      if (!tab) return { ok: false, error: "Nenhuma aba ativa." };
      await chrome.tabs.update(tab.id, { url: cmd.url });
      await new Promise(resolve => {
        const listener = (tabId, info) => {
          if (tabId === tab.id && info.status === "complete") {
            chrome.tabs.onUpdated.removeListener(listener);
            setTimeout(resolve, 600);
          }
        };
        chrome.tabs.onUpdated.addListener(listener);
        setTimeout(() => { chrome.tabs.onUpdated.removeListener(listener); resolve(); }, 7000);
      });
      const res = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: domInspectorAndActuator,
        args: [{ mode: "EXTRACT", ...(cmd.extract_options || {}), max_chars: 3000 }]
      });
      const resultObj = res[0]?.result || { ok: false };
      resultObj.tab_id = tab.id;
      return resultObj;
    }

    if (cmd.action === "DOM_ACTION") {
      const tab = Number.isInteger(cmd.tab_id) ? await chrome.tabs.get(cmd.tab_id)
        : (await chrome.tabs.query({ active: true, lastFocusedWindow: true }))[0];
      if (!tab) return { ok: false, error: "Nenhuma aba ativa encontrada." };
      const res = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: domInspectorAndActuator,
        args: [cmd.payload || { mode: "EXTRACT" }]
      });
      return res[0]?.result || { ok: false, error: "Falha ao injetar no DOM." };
    }

    if (cmd.action === "TAB_STATE") {
      const window = await chrome.windows.getLastFocused();
      const tabs = await chrome.tabs.query({ windowId: window.id });
      return { ok: true, focused: window.focused, window_id: window.id,
        tabs: tabs.map((tab) => ({ id: tab.id, active: tab.active, window_id: tab.windowId })) };
    }

    if (cmd.action === "CLOSE_TABS") {
      const ids = (cmd.tab_ids || []).filter(Boolean);
      if (ids.length > 0) {
        try {
          await chrome.tabs.remove(ids);
          return { ok: true, closed_count: ids.length };
        } catch (e) {
          return { ok: false, error: String(e) };
        }
      }
      return { ok: true, closed_count: 0 };
    }

    return { ok: false, error: "Ação desconhecida." };
  } catch (err) {
    return { ok: false, error: String(err) };
  }
}

async function startLongPoll() {
  if (pollingActive) return;
  pollingActive = true;
  try {
    const config = await chrome.storage.local.get("bridgeToken");
    const token = config.bridgeToken;
    if (typeof token !== "string" || !/^[0-9a-f]{64}$/.test(token)) return;
    const headers = {"X-Brainnet-Token":token};
    while (pollingActive) {
      const settings = await chrome.storage.local.get("bridgeToken");
      if (settings.bridgeToken !== token) break;
      try {
        const resp = await fetch(BRIDGE_URL+"/poll", {method:"GET",headers,credentials:"omit",cache:"no-store",redirect:"error",signal:AbortSignal.timeout(12000)});
        if (resp.status === 403) break;
        if (!resp.ok) throw Error("Bridge unavailable");
        const cmd = await resp.json();
        if (cmd && /^[0-9a-f]{10}$/.test(cmd.id || "") && typeof cmd.action === "string" && cmd.action !== "IDLE") {
          const latest = await chrome.storage.local.get("bridgeToken");
          if (latest.bridgeToken !== token) break;
          const result = await handleCommand(cmd);
          const body = JSON.stringify({id:cmd.id,result});
          await fetch(BRIDGE_URL+"/result",{method:"POST",headers:{...headers,"Content-Type":"application/json"},credentials:"omit",redirect:"error",body,signal:AbortSignal.timeout(5000)});
        }
      } catch (_) { await new Promise(r=>setTimeout(r,2000)); }
    }
  } finally { pollingActive = false; }
}
chrome.storage.onChanged.addListener((changes,area)=>{
  if (area === "local" && changes.bridgeToken && !pollingActive) startLongPoll();
});
startLongPoll();
