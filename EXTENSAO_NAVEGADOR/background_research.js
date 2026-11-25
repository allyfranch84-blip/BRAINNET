/* Dedicated read-only research; no clicks, focus, or physical coordinates. */
function extractGoogleResults() {
  const links = [];
  const seen = new Set();
  for (const heading of document.querySelectorAll('#search a h3, #rso a h3')) {
    const anchor = heading.closest('a');
    const title = (heading.innerText || heading.textContent || '').trim().slice(0, 160);
    try {
      const url = new URL(anchor.href);
      if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || !title || seen.has(url.href)) continue;
      if (url.hostname === 'www.google.com' && url.pathname === '/search') continue;
      seen.add(url.href);
      links.push({title, url: url.href});
      if (links.length >= 15) break;
    } catch (_) { /* invalid link */ }
  }
  return {url: location.href, title: document.title.slice(0, 160), links};
}

async function runBackgroundResearch(cmd, api, sleep = ms => new Promise(r => setTimeout(r, ms))) {
  if (typeof cmd.query !== 'string' || !cmd.query.trim() || cmd.query.length > 500) return {ok:false, error:'Invalid query'};
  let owned = null, result = {ok:false, error:'Incomplete research'};
  try {
    const win = await api.windows.getLastFocused();
    if (!Number.isInteger(win.id)) throw Error('No browser window');
    const [before] = await api.tabs.query({windowId:win.id, active:true});
    if (!before) throw Error('No active tab for comparison');
    const url = new URL('https://www.google.com/search');
    url.searchParams.set('q',cmd.query.trim());
    const tab = await api.tabs.create({windowId:win.id, url:url.href, active:false});
    if (!Number.isInteger(tab.id)) throw Error('Tab creation unconfirmed');
    owned = tab.id;
    let current;
    for (let i=0;i<32;i++) {
      current = await api.tabs.get(owned);
      if (current.active || current.windowId !== win.id) throw Error('Tab taken over or moved');
      if (current.status === 'complete') break;
      await sleep(250);
    }
    if (current.status !== 'complete') throw Error('Navigation timeout');
    const loaded = new URL(current.url);
    if (loaded.origin !== 'https://www.google.com' || loaded.pathname !== '/search') throw Error('Unexpected redirect');
    const [response] = await api.scripting.executeScript({target:{tabId:owned},func:extractGoogleResults});
    if (!response?.result || !Array.isArray(response.result.links) || response.result.url !== current.url) throw Error('Extraction not confirmed');
    const [after] = await api.tabs.query({windowId:win.id,active:true});
    result = {ok:response.result.links.length>0, ...response.result, tab_id:owned,
      browser_active_tab_unchanged:after?.id===before.id, mode:'BACKGROUND_READ_ONLY'};
    if (!result.ok) result.error='No organic results observed';
  } catch (error) { result = {ok:false,error:String(error.message||error)}; }
  finally {
    if (owned !== null) {
      try {
        const tab = await api.tabs.get(owned);
        if (tab.active) result.cleanup='USER_ACTIVE_TAB_PRESERVED';
        else { await api.tabs.remove(owned); result.cleanup='OWNED_TAB_REMOVED'; }
      } catch (_) { result.cleanup='UNCONFIRMED'; }
    }
  }
  return result;
}
if (typeof module !== 'undefined' && module.exports) module.exports = {runBackgroundResearch};
