// ── Remembered selections ─────────────────────────────────────────────────────
// Chat place · filter chip and the token range survive a refresh (mode, session filters, structure
// project/scope/tests/axis/kinds have their own keys). Saved when the page hides; only the main window saves.
// Per browser tab (08 tabGet/tabSet): a refresh restores this tab's own choices, a new tab starts from the last saved.
// ⚠Restored values are shape-checked here; a room that is gone falls back to the room list (buildRooms, 92).
const UIK_KEY = 'sidereus.ui';
function uiKeepSnap(){ return { place: place, filter: filter, wkr: WKRANGE }; }   // an old saved byThread key is ignored
function uiKeepOk(v){ return typeof v === 'string' && v.length > 0 && v.length <= 200 && !/[\n\r]/.test(v); }
function uiKeepApply(s){
  if(!s || typeof s !== 'object') return;
  if(uiKeepOk(s.place) && (s.place === 'dm' || s.place.indexOf('room:') === 0)) place = s.place;
  if(uiKeepOk(s.filter)) setFilter(s.filter);
  if(Object.prototype.hasOwnProperty.call(WKR_LABEL, s.wkr)) WKRANGE = +s.wkr;
}
// Timeline «Changed» rail: followed session · repo chip · base mode.
// ⚠A session/repo that is gone falls back silently: tlgTarget drops a missing tlgSel once SESS is loaded, a missing repo shows the cwd.
const TLGK_KEY = 'sidereus.tlgsel';
function tlgKeepSnap(){ return { sel: tlgSel, rkey: tlgRepoSel.key, repo: tlgRepoSel.repo, mode: tlgMode }; }
function tlgKeepApply(s){
  if(!s || typeof s !== 'object') return;
  if(uiKeepOk(s.sel) && /^[sc]:/.test(s.sel)) tlgSel = s.sel;
  if(uiKeepOk(s.rkey) && uiKeepOk(s.repo) && s.repo.charAt(0) === '/') tlgRepoSel = {key: s.rkey, repo: s.repo};
  if(s.mode === 'auto' || TLG_MODES.some(m => m[0] === s.mode)) tlgMode = s.mode;
}
function tlgKeepSave(){ if(!ISPOP && !ISWP && !ISBP) tabSetJson(TLGK_KEY, tlgKeepSnap()); }
if(!ISPOP && !ISWP && !ISBP){
  try{ tlgKeepApply(JSON.parse(tabGet(TLGK_KEY, 'null'))); }catch(e){ softErr('tlgkeep-read', e); }
  addEventListener('pagehide', tlgKeepSave);
}
if(!ISPOP && !ISWP && !ISBP){
  try{ uiKeepApply(JSON.parse(tabGet(UIK_KEY, 'null'))); }catch(e){ softErr('uikeep-read', e); }
  const uiKeepSave = () => { tabSetJson(UIK_KEY, uiKeepSnap()); };
  addEventListener('pagehide', uiKeepSave);
  document.addEventListener('visibilitychange', () => { if(document.hidden) uiKeepSave(); });
}
