/* UIS = UI prefs in memory, seeded from window.__UIP (GET /api/ui-prefs.js, a blocking script before this one) and
   written back as debounced per-key deltas to POST /api/ui-prefs. Same surface as localStorage: getItem/setItem/removeItem/
   key/length/clear, plus UIS.x · UIS[k]=v · delete UIS[k] · Object.keys(UIS). Values are strings, like localStorage.
   __UIP undefined = the prefs script failed ⇒ defaults in memory, nothing posted. null = no prefs file yet ⇒ one-time copy
   of this browser's localStorage prefs, posted once with _v:1.
   ⚠localStorage is never cleared or written here (rollback copy). 88e-rvnotes drafts (need the cross-tab storage event)
   and the 43-notify permission keys stay in localStorage and are not migrated.
   ⚠fetch keepalive carries at most 64 KB: values over 16 KB flush at once, the pagehide flush drops keepalive when too big. */
var UIS=(function(){
  // ⚠Automated pages read the owner's prefs but never post: a stray click would overwrite them.
  // ⚠MCP playwright browsers report webdriver=false ⇒ automation opens ?nosave=1 (kept in sessionStorage for in-app navigation).
  var wd=false;try{wd=window.navigator.webdriver===true;}catch(e){wd=false;}
  try{var SS=window.sessionStorage;if(/[?&]nosave=1(&|$)/.test((window.location&&window.location.search)||'')){wd=true;if(SS)SS.setItem('sidereus.nosave','1');}
    else if(SS&&SS.getItem('sidereus.nosave')==='1')wd=true;}catch(e){}
  var M=Object.create(null),up=window.__UIP,on=up!==undefined&&!wd,P={},D={},tm=0,dead=false,LS=null;
  try{LS=window.localStorage;}catch(e){LS=null;}
  function requeue(set,del){   // a failed POST goes back to the queue unless the key changed since; the next write retries
    Object.keys(set).forEach(function(k){if(!(k in P)&&!(k in D)&&M[k]===set[k])P[k]=set[k];});
    del.forEach(function(k){if(!(k in M)&&!(k in P))D[k]=1;});
  }
  function send(set,del,keep){
    if(!on||dead)return;
    // ⚠The server refuses a value over 64 KB: keep it in memory only, never post it (it would fail the whole batch).
    Object.keys(set).forEach(function(k){if(typeof set[k]==='string'&&set[k].length>65536){delete set[k];console.warn('[UIS] not saved, over 64 KB:',k);}});
    if(!Object.keys(set).length&&!del.length)return;
    var b=JSON.stringify({set:set,del:del}),mig='_v' in set;
    try{fetch('/api/ui-prefs',{method:'POST',headers:{'Content-Type':'application/json'},body:b,credentials:'same-origin',keepalive:!!keep&&b.length<60000})
      .then(function(r){
        if(r.ok)return;
        // ⚠4xx = the batch itself is refused: drop it (a requeue would repeat it forever); a refused migration still marks _v.
        if(r.status>=400&&r.status<500){console.warn('[UIS] batch refused: HTTP '+r.status);if(mig&&Object.keys(set).length>1)send({_v:1},[],false);return;}
        throw new Error('HTTP '+r.status);})
      .catch(function(e){requeue(set,del);console.warn('[UIS] save failed:',e);});}
    catch(e){requeue(set,del);console.warn('[UIS] save failed:',e);}
  }
  function flush(keep){
    if(tm){clearTimeout(tm);tm=0;}
    var s=P,d=Object.keys(D);
    if(!Object.keys(s).length&&!d.length)return;
    P={};D={};send(s,d,keep);
  }
  function later(big){if(!on||dead)return;if(tm)clearTimeout(tm);tm=0;if(big)flush(false);else tm=setTimeout(flush,400);}
  var api={
    getItem:function(k){k=String(k);return k in M?M[k]:null;},
    setItem:function(k,v){k=String(k);v=String(v);if(M[k]===v)return;M[k]=v;P[k]=v;delete D[k];later(v.length>16384);},
    removeItem:function(k){k=String(k);if(!(k in M))return;delete M[k];delete P[k];D[k]=1;later(false);},
    key:function(i){var a=Object.keys(M);return i>=0&&i<a.length?a[i]:null;},
    clear:function(){Object.keys(M).forEach(api.removeItem);},
    flush:function(){flush(false);},
    // «Reset display settings»: the server already reset the file; drop everything and never post again before the reload.
    wipe:function(){M=Object.create(null);P={};D={};if(tm)clearTimeout(tm);tm=0;dead=true;}
  };
  if(up&&typeof up==='object')Object.keys(up).forEach(function(k){var v=up[k];if(k!=='_v'&&v!==null&&v!==undefined)M[k]=typeof v==='string'?v:JSON.stringify(v);});
  else if(up===null){
    var RE=/^(mb|sidereus\.|agPH$|dfW$)/,NO=/^(sidereus\.rvnotes\.|sidereus\.notify$|sidereus\.osntf$)/,s={};
    try{if(LS)for(var i=0;i<LS.length;i++){var k=LS.key(i);if(k!==null&&RE.test(k)&&!NO.test(k)){var v=LS.getItem(k);if(v!==null)M[k]=v;}}}
    catch(e){console.warn('[UIS] migration read failed:',e);}
    Object.keys(M).forEach(function(k){s[k]=M[k];});
    s._v=1;send(s,[],false);
  }
  if(on)try{window.addEventListener('pagehide',function(){flush(true);});}catch(e){console.warn('[UIS] pagehide:',e);}
  return new Proxy({},{
    get:function(t,p){if(typeof p!=='string')return undefined;if(p==='length')return Object.keys(M).length;
      if(Object.prototype.hasOwnProperty.call(api,p))return api[p];return p in M?M[p]:undefined;},
    set:function(t,p,v){api.setItem(p,v);return true;},
    deleteProperty:function(t,p){api.removeItem(p);return true;},
    has:function(t,p){return typeof p==='string'&&p in M;},
    ownKeys:function(){return Object.keys(M);},
    getOwnPropertyDescriptor:function(t,p){return typeof p==='string'&&p in M?{value:M[p],writable:true,enumerable:true,configurable:true}:undefined;}
  });
})();
/* The "next" UI is the main UI (2026-09-23). Set before CSS paints so the old look never flashes. */
document.documentElement.dataset.ui='next';try{var t0=UIS.mbTone;document.documentElement.dataset.tone=(t0==='grey'||t0==='blue')?t0:'black';}catch(e){document.documentElement.dataset.tone='black';}
/* mbTone white/system -> data-theme before first paint; system in OS dark uses the last dark tone (mbToneDk).
   ⚠No stored (or unknown) tone = system, the same default as tonePref() in 90-settings.js — they must agree or the page flashes. */
try{if(UIS.mbTheme){if(UIS.mbTheme==='light')UIS.mbTone='white';UIS.removeItem('mbTheme');}var t1=UIS.mbTone,dk1=UIS.mbToneDk;if(['black','grey','blue','white','system'].indexOf(t1)<0)t1='system';if(t1==='system'&&(dk1==='grey'||dk1==='blue'))document.documentElement.dataset.tone=dk1;document.documentElement.dataset.theme=(t1==='white'||(t1==='system'&&matchMedia('(prefers-color-scheme: light)').matches))?'light':'dark';}catch(e){try{document.documentElement.dataset.theme=matchMedia('(prefers-color-scheme: light)').matches?'light':'dark';}catch(e2){document.documentElement.dataset.theme='dark';}}
/* mbFs text scale (90/100/110/125 %) -> --fs before first paint. ⚠Same normalisation as fsPref() in 90-settings.js or the page flashes. */
try{var f1=UIS.mbFs;if(['90','110','125'].indexOf(f1)>=0)document.documentElement.style.setProperty('--fs',String(f1/100));}catch(e){}