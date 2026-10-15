// Automation banner: a thin non-blocking strip on windows driven by playwright/CDP (navigator.webdriver), so they are not mistaken for the user's tab.
// Pure: shown only under automation; ?autobar=0 hides it (scripts/screen_check.mjs appends it so the screen baseline stays unchanged).
function autobarShould(webdriver, search){
  let q = null; try{ q = new URLSearchParams(search || '').get('autobar'); }catch(e){ softErr('autobarQ', e); }
  return !!webdriver && q !== '0';
}
function autobarInit(){
  if(!autobarShould(navigator.webdriver === true, location.search) || document.getElementById('autobar')) return;
  const el = document.createElement('div');
  el.id = 'autobar'; el.setAttribute('role', 'note');
  el.textContent = T('Automated test window — opened by an agent, not your tab');   // ⚠text set once; a language switch shows on the next load
  document.body.appendChild(el);
}
if(document.body) autobarInit(); else addEventListener('DOMContentLoaded', autobarInit);
