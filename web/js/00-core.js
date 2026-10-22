
const MY_BUILD = '__PAGE_BUILD__';     // filled in by the server (PAGE_BUILD)
const PAGE_NAME = 'Sidereus';         // tab title — '(3) Sidereus' when there are unread items
// Selectors allowed below the 12px floor -> their minimum px (selector text as written in web/css). Each needs a reason.
const FS_KEEP = {};
// Font size for one declared value: px -> ladder (+1 body, +2 from 14px) if laddered, 12px floor, x --fs; var() -> x --fs.
// <8px (icon/glyph tricks) and anything else ('' = leave the rule alone).
function fsSize(v, laddered, floor){
  v = String(v || '').trim();
  if(/^var\(/.test(v)) return 'calc(' + v + ' * var(--fs,1))';
  const m = /^([\d.]+)px$/.exec(v); if(!m) return '';
  let n = +m[1]; if(n < 8) return '';
  if(laddered) n = n <= 13.5 ? n + 1 : n + 2;
  return 'calc(' + Math.max(floor == null ? 12 : floor, n) + 'px * var(--fs,1))';
}
// Rewrites every rule's font-size in place (floor + --fs) and widens px line-heights below the new size.
// ⚠Run once, after #nxcss/#nxlt exist: afterwards sizes are calc(), which neither the ladder nor this can parse again.
function fsApply(){
  const walk = (rs, top, own) => { for(const r of rs){
    if(r.cssRules && !(r instanceof CSSStyleRule)){ walk(r.cssRules, false, own); continue; }
    if(!(r instanceof CSSStyleRule)) continue;
    const st = r.style, fs = st.getPropertyValue('font-size'); if(!fs) continue;
    const sel = r.selectorText, kp = FS_KEEP[sel.replace(/^html\[data-ui=next\] /, '')];
    // top-level rules were twinned by the ladder, data-ui rules opt out of it; nested @media rules never saw it
    const dui = own || sel.includes('data-ui'), lad = !dui && !top;
    const v = fsSize(fs, lad, kp); if(!v) continue;
    st.setProperty('font-size', v, st.getPropertyPriority('font-size'));
    // line-height compares with the size that actually renders (the twin's, for top-level rules)
    const lh = /^([\d.]+)px$/.exec(st.getPropertyValue('line-height')), eff = /^calc\(([\d.]+)px/.exec(fsSize(fs, !dui, kp));
    if(lh && eff && +lh[1] < +eff[1]) st.setProperty('line-height', 'max(' + lh[1] + 'px, 1.2em)', st.getPropertyPriority('line-height'));
  } };
  for(const sh of document.styleSheets){ let rs; try { rs = sh.cssRules; } catch(e){ continue; }
    const id = sh.ownerNode && sh.ownerNode.id; walk(rs, true, id === 'nxcss' || id === 'nxlt'); }
}
// The former ?ui=next preview is the only UI (2026-09-23). data-ui/data-tone are set by the <head> script.
{
  // Type/contrast ladder + Sidereus palette (tokens in 90-main-ui.css) under the flag. The stylesheet hard-codes ~300 px sizes and
  // colors, so instead of forking every rule we emit a flagged twin of each one. ⚠Twins are emitted for EVERY
  // rule with a size or color (mapped or not) so the original cascade order is preserved (+0,1,1 on all of them).
  try{
    const GRAY = {'#6b7688':'var(--nx-t3)','#7e8896':'var(--nx-t2)','#8b95a7':'var(--nx-t2)','#dfe5ee':'var(--nx-t1)'};
    const rgba = c => { const m = /^rgba?\((\d+), (\d+), (\d+)(?:, ([\d.]+))?\)$/.exec(c||'');
      return m ? [+m[1], +m[2], +m[3], m[4] == null ? 1 : +m[4]] : null; };
    const hex = c => { const v = rgba(c); return v && v[3] === 1
      ? '#' + v.slice(0,3).map(x => x.toString(16).padStart(2,'0')).join('') : ''; };
    const hsl = (r, g, b) => { r/=255; g/=255; b/=255; const mx = Math.max(r,g,b), mn = Math.min(r,g,b), l = (mx+mn)/2, d = mx-mn;
      if(!d) return [0, 0, l, 0]; const s = d / (1 - Math.abs(2*l - 1));
      const h = mx === r ? ((g-b)/d + 6) % 6 : mx === g ? (b-r)/d + 2 : (r-g)/d + 4; return [h*60, s, l, d]; };
    const out = (h, s, l, a) => 'hsl(' + h + ' ' + (s*100).toFixed(1) + '% ' + (l*100).toFixed(1) + '% / ' + a + ')';
    // Dark neutral surfaces/borders snap to the tone variables (so «Background tone» reaches hard-coded rules); other neutrals
    // go grey; blue/green/yellow/red accents move to the Sidereus semantic hues at the same lightness. kind: 'text'|'bg'|'border'.
    // ⚠The HSL hues below (215/115/49/356) are the sRGB HSL hues of --nx-info/ok/warn/err — change them together.
    // ⚠Per-session hue classes (.c0-.c6) are skipped so sessions stay distinguishable.
    const tone = (c, sel, kind) => { const v = rgba(c); if(!v || /\.c\d\b/.test(sel)) return c;
      const [h, s, l, d] = hsl(v[0], v[1], v[2]), a = v[3], cool = h >= 190 && h <= 245;
      const sv = x => a === 1 ? 'var(' + x + ')' : 'color-mix(in srgb, var(' + x + ') ' + Math.round(a*100) + '%, transparent)';
      if(d <= 0.05 || (cool && d <= 0.18)){
        if(kind === 'bg' && l < 0.16) return sv(l < 0.08 ? '--nx-bg' : l < 0.115 ? '--nx-panel' : '--nx-hover');
        if(kind === 'border' && l < 0.2) return sv('--nx-rule');
        return out(kind === 'text' ? 240 : 220, kind === 'text' ? 0.08 : 0.05, l, a); }
      if(cool && s > 0.35) return out(215, Math.max(0.6, Math.min(0.87, s)), l, a);
      if(s > 0.3 && h >= 85 && h <= 170) return out(115, Math.min(0.42, s), l, a);
      if(s > 0.4 && h >= 42 && h <= 62) return out(49, Math.min(0.95, s), l, a);
      if(s > 0.4 && (h <= 12 || h >= 340)) return out(356, Math.min(0.88, s), l, a);
      return c; };
    // Light-theme twin of one color: dark neutrals -> tokens/light greys, light text -> dark, accents darkened for >=4.5 contrast.
    const lite = (c, kind) => { const v = rgba(c); if(!v) return c;
      const [h, s, l, d] = hsl(v[0], v[1], v[2]), a = v[3], neu = d <= 0.05 || (h >= 190 && h <= 245 && d <= 0.18);
      if(kind === 'fill') kind = neu ? 'text' : 'bg';   // SVG fill is mostly text/labels when neutral
      const sv = x => a === 1 ? 'var(' + x + ')' : 'color-mix(in srgb, var(' + x + ') ' + Math.round(a*100) + '%, transparent)';
      if(kind === 'shadow') return !neu ? c : l < 0.5 ? out(h, s, l, +(a*0.45).toFixed(3)) : out(h, s, 1 - l, a);
      if(neu){
        if(kind === 'text') return l >= 0.45 ? out(h, s, 0.1 + (1 - l)*0.66, a) : c;
        if(kind === 'bg' && l < 0.16) return sv(l < 0.08 ? '--nx-bg' : l < 0.115 ? '--nx-panel' : '--nx-hover');
        if(kind === 'border' && l < 0.2) return sv('--nx-rule');
        if(l > 0.6) return a < 1 ? out(h, s, 1 - l, a) : c;
        return out(h, s, kind === 'border' ? 0.88 - Math.max(0, l - 0.2)*0.6 : 0.94 - Math.max(0, l - 0.16)*0.5, a); }
      if(kind === 'text') return out(h, s, Math.min(l, h >= 35 && h <= 200 ? 0.3 : h > 12 && h < 35 ? 0.36 : 0.42), a);
      if(a === 1 && l < 0.4) return kind === 'border' ? out(h, Math.min(s, 0.6), 0.82 - l*0.2, 1) : out(h, Math.min(s, 0.7), 0.95 - l*0.25, 1);
      return c; };
    const LPROP = [['color','color','text'],['backgroundColor','background-color','bg'],['borderTopColor','border-top-color','border'],
                   ['borderRightColor','border-right-color','border'],['borderBottomColor','border-bottom-color','border'],
                   ['borderLeftColor','border-left-color','border'],['outlineColor','outline-color','border'],['fill','fill','fill'],
                   ['stroke','stroke','border'],['backgroundImage','background-image','bg'],['boxShadow','box-shadow','shadow']];
    const BPROP = [['backgroundColor','background-color'],['borderTopColor','border-top-color'],['borderRightColor','border-right-color'],
                   ['borderBottomColor','border-bottom-color'],['borderLeftColor','border-left-color'],['outlineColor','outline-color']];
    // Ladder + 12px floor + --fs scale live in fsSize(). ⚠px only here: a var() twin would outrank later data-ui rules.
    const fsz = (v, sel) => /^[\d.]+px$/.test(v||'') ? fsSize(v, true, FS_KEEP[sel]) : '';
    const split = s => { const out = []; let d = 0, cur = '';
      for(const ch of s){ if(ch === '(') d++; else if(ch === ')') d--;
        if(ch === ',' && !d){ out.push(cur); cur = ''; } else cur += ch; }
      out.push(cur); return out.map(x => x.trim()).filter(Boolean); };
    const pre = sel => split(sel).map(p => p.startsWith(':root') ? 'html[data-ui=next]'
      : (/^html\b/.test(p) ? p.replace(/^html/, 'html[data-ui=next]') : 'html[data-ui=next] ' + p)).join(',');
    let css = '', lcss = '';
    for(const sh of document.styleSheets){ let rs; try { rs = sh.cssRules; } catch(e){ continue; }
      for(const r of rs){
        if(!(r instanceof CSSStyleRule) || r.selectorText.includes('data-ui')) continue;
        const sel = r.selectorText, f = fsz(r.style.fontSize, sel), c = r.style.color, g = GRAY[hex(c)];
        // ⚠:where() keeps light twins at the dark twins' specificity, so they win only by coming later (same cascade).
        const lp = LPROP.filter(p => r.style[p[0]]).map(p => p[1] + ':' + (p[0] === 'color' && g ? g
          : r.style[p[0]].replace(/rgba?\([^)]*\)/g, m => lite(m, p[2]))) + ';').join('');
        if(lp) lcss += pre(sel).split('html[data-ui=next]').join('html[data-ui=next]:where([data-theme=light])') + '{' + lp + '} ';
        const bp = BPROP.filter(p => r.style[p[0]]).map(p => p[1] + ':' + tone(r.style[p[0]], sel, p[0] === 'backgroundColor' ? 'bg' : 'border') + ';').join('');
        if(!f && !c && !bp) continue;
        css += pre(sel) + '{' + (f ? 'font-size:' + f + ';' : '')
             + (c ? 'color:' + (g && !/\.c\d\b/.test(sel) ? g : tone(c, sel, 'text')) + ';' : '') + bp + '} ';
      } }
    const st = document.createElement('style'); st.id = 'nxcss'; st.textContent = css; document.head.appendChild(st);
    const lt = document.createElement('style'); lt.id = 'nxlt'; lt.textContent = lcss; document.head.appendChild(lt);
  }catch(e){ softErr('nxcss', e); }
  try{ fsApply(); }catch(e){ softErr('fsApply', e); }
}
// Theme-aware literal for JS-drawn colors (canvas/SVG attributes can't read --nx-*): dark value first, light second.
const thc = (dk, lt) => document.documentElement.dataset.theme === 'light' ? lt : dk;
const NL = String.fromCharCode(10);
// ★Quotes are escaped too. It used to escape only `& < >`, so **a quote inside `title="..."` ended
//   the attribute right there** — tooltips were silently truncated (measured 2026-09-02: verdict tooltip cut before `"`).
//   This file puts commands, paths and descriptions into tooltips in many places, so the same truncation was likely widespread.
//   In HTML text positions `&quot;` also renders as a quote, so both uses are safe.
const esc = s => String(s).replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// Display-only: drop a leading pipeline machine tag ([pl:-] · [pl:<name>/<stage>] · [pl-skip:…] · [pl-model:…]) from an agent
// label, also right after a «type: » prefix. ⚠Never apply to the raw field: plDescStage/plTagNames/wpRunOf match on the tag.
// Regex kept inline so tests can lift the function alone (tests/_load.py js_fn).
function plStrip(s){ return s == null ? s : String(s).replace(/^((?:[^\s:]{1,60}: )?)\s*\[pl(?:-skip|-model|-agent|-none)?:[^\]\n]{0,160}\]\s*/, '$1'); }
// 8-char display id for a session — mirrors sidereus/ident.py _sid8. ⚠Plain slice(0,8) of a gemini/codex file-stem id
// shows «session-»/«rollout-» for every row. Display only: never a lookup key.
function sid8(s){
  let v = s ? String(s) : '';
  for(const p of ['session-', 'rollout-']) if(v.startsWith(p)){
    v = v.slice(p.length).replace(/^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}(?:-\d{2})?-/, ''); break;
  }
  return v.slice(0, 8);
}
// Number rules (one place): suffixes K/M/B always uppercase · fmtPct/fmtMoney below · fmtSelfTest() checks them.
// Token count -> K/M/B. o.dec = B decimals (1), o.zero = any falsy n prints '0'. ⚠o.k (lowercase 'k') is ignored now.
function fmtTok(n, o){
  o = o || {};
  if(o.zero && !n) return '0';
  // ⚠Thresholds at 999.5 of the lower unit: Math.round would otherwise print «1000K»/«1000M» (same guard as fmtMoney).
  if(n >= 999.5e6) return (n/1e9).toFixed(o.dec == null ? 1 : o.dec)+'B';
  if(n >= 999.5e3) return Math.round(n/1e6)+'M';
  if(n >= 999.5) return Math.round(n/1e3)+'K';
  return String(n);
}
// Percent (0-100 scale): whole number; one decimal only under 10 when not whole; any non-zero share under 1 is '<1%'.
function fmtPct(p){
  if(p == null || !isFinite(p)) return '—';
  if(p <= 0) return Math.round(p) + '%';
  if(p < 1) return '<1%';
  const s = p.toFixed(1);
  return (p < 10 && !/\.0$/.test(s) ? s : String(Math.round(p))) + '%';
}
// Dollars: 2 significant digits under 10 (of the unit), whole above, cents under $1; K/M like fmtTok ($0.03 $5.0 $12 $2.6K $26K).
function fmtMoney(c){
  if(c == null || !isFinite(c)) return '—';
  const a = Math.abs(c), sg = c < 0 ? '-' : '';
  if(!a) return '$0';
  if(a < 0.01) return sg + '<$0.01';
  const [v, u] = a >= 999.5e3 ? [a/1e6, 'M'] : a >= 999.5 ? [a/1e3, 'K'] : [a, ''];
  return sg + '$' + (!u && v < 1 ? v.toFixed(2) : v < 9.95 ? v.toPrecision(2) : String(Math.round(v))) + u;
}
// Character count: under 1000 exact, then one-decimal K (the chat meta «1.2K chars»).
function fmtChars(n){ return n < 1000 ? String(n) : (Math.round(n/100)/10) + 'K'; }
// Returns the list of failing cases ([] = pass); run by tests/test_fmt_rules.py through node.
function fmtSelfTest(){
  const cases = [[fmtPct(61.5), '62%'], [fmtPct(16.67), '17%'], [fmtPct(6.3), '6.3%'], [fmtPct(6.02), '6%'], [fmtPct(9.97), '10%'],
    [fmtPct(0.26), '<1%'], [fmtPct(0), '0%'], [fmtPct(100), '100%'], [fmtPct(null), '—'],
    [fmtMoney(0.456), '$0.46'], [fmtMoney(0.03), '$0.03'], [fmtMoney(5), '$5.0'], [fmtMoney(9.96), '$10'], [fmtMoney(121.94), '$122'], [fmtMoney(0), '$0'],
    [fmtMoney(2600), '$2.6K'], [fmtMoney(1410.3), '$1.4K'], [fmtMoney(26400), '$26K'], [fmtMoney(999.6), '$1.0K'], [fmtMoney(0.004), '<$0.01'],
    [fmtTok(1234), '1K'], [fmtTok(5e6), '5M'], [fmtTok(2.1e9), '2.1B'],
    [fmtTok(999499), '999K'], [fmtTok(999600), '1M'], [fmtTok(999.4e6), '999M'], [fmtTok(999.6e6), '1.0B'], [fmtTok(999), '999'], [fmtChars(640), '640'], [fmtChars(1234), '1.2K'],
    // Every «N min ago» goes through ago(), which floors: 90-119s is «1 min» on every screen.
    [ago(59), U(59,'s')], [ago(90), U(1,'m')], [ago(119), U(1,'m')], [ago(3599), U(59,'m')], [ago(3600), U(1,'h')]];
  return cases.filter(c => c[0] !== c[1]).map(c => c[0] + ' != ' + c[1]);
}
const inline = s => esc(s).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
// ── digest — **shrinks long text to 3 lines (zero cost).** No LLM; looks only at markdown structure.
//   Why: text was too verbose. Measured: body median **1800 chars** · 86% over 1000 chars ·
//   1% under 200. The screen cut to the first 220px, but **the beginning is usually preamble**,
//   so the point was invisible. Hence **key lines are extracted** instead of truncating.
//   Evidence (bus.jsonl, 384 measured): `**bold**` 89% · `★` 45% · `##` heading 52% — these three carry the point.
function digest(src){
  const raw=String(src||'').split('\n');
  const out=[], seen=new Set();
  const clean=t=>t.replace(/^[#>\-*\s★⚠✅❌⛔🔶]+/,'').replace(/\*\*/g,'').replace(/`/g,'').trim();
  let inCode=false, code=0, table=0;
  for(const ln of raw){
    if(/^```/.test(ln)){ inCode=!inCode; if(inCode) code++; continue; }
    if(inCode) continue;
    if(/^\s*\|.*\|/.test(ln)){ table++; continue; }
    const t=ln.trim(); if(!t) continue;
    // Priority: ★ mark > bold > heading (by **strength of intent**, not by measured ratio)
    const rank = t.startsWith('★')||t.includes('★') ? 0 : /\*\*[^*]{6,}\*\*/.test(t) ? 1 : /^#{2,}\s/.test(t) ? 2 : 9;
    if(rank===9) continue;
    const c=clean(t); if(c.length<6||seen.has(c)) continue;
    seen.add(c); out.push({rank,text:c.slice(0,160)});
  }
  out.sort((a,b)=>a.rank-b.rank);
  let picks=out.slice(0,3).map(x=>x.text);
  if(!picks.length){                       // no marks → first paragraph (preamble is better than nothing)
    const first=raw.map(x=>x.trim()).filter(x=>x&&!/^```/.test(x))[0]||'';
    if(first) picks=[clean(first).slice(0,160)];
  }
  const chars=String(src||'').length;
  const meta=[T('{n} chars').replace('{n}', fmtChars(chars)), table?T('{n} tables').replace('{n}', table):'', code?T('{n} code blocks').replace('{n}', code):'']
    .filter(Boolean).join(' · ');
  return {picks, meta, long: chars>600};
}

// ★Code coloring — no library (zero cost · zero external deps). No exact language parsing, **common tokens only**:
//   comments · strings · numbers · keywords. Code in this room mixes java/sql/js/sh/json, so
//   per-language grammars aren't worth it — the goal is "looks like code", not exact parsing.
// ★The source is split into tokens first, then **each token is escaped separately**. Running regexes over an already-escaped string
//   cuts inside `&amp;` and breaks entities (a common real-world accident).
// ★Per-language keywords (code is detected by extension). One combined set colors SQL's SELECT
//   in Java and Java's class in SQL — knowing the language from the extension removes those false hits.
//   Unknown language (no extension, no fence language) falls back to KW (combined) below.
const LKW = {
  java:'abstract,assert,boolean,break,byte,case,catch,char,class,companion,const,continue,data,default,do,'
      +'double,else,enum,extends,final,finally,float,for,fun,goto,if,implements,import,init,instanceof,int,'
      +'interface,internal,lateinit,long,native,new,object,open,operator,override,package,permits,private,'
      +'protected,public,record,return,sealed,short,static,strictfp,super,suspend,switch,synchronized,this,'
      +'throw,throws,transient,try,val,var,void,volatile,when,while,yield,true,false,null',
  sql:'select,from,where,join,left,right,inner,outer,full,cross,on,using,group,order,by,having,limit,offset,'
     +'insert,into,values,update,set,delete,merge,create,alter,drop,truncate,rename,table,index,view,sequence,'
     +'trigger,procedure,function,database,schema,and,or,not,null,as,distinct,union,all,case,when,then,else,'
     +'end,exists,in,between,like,is,asc,desc,primary,key,foreign,references,unique,check,default,constraint,'
     +'comment,grant,revoke,with,partition,over,rownum,dual,begin,commit,rollback,declare,cursor,add,modify,'
     +'column,cascade,replace,if,int,varchar,varchar2,number,date,timestamp,char,clob,blob,text,bigint',
  js:'as,async,await,break,case,catch,class,const,continue,debugger,declare,default,delete,do,else,enum,'
    +'export,extends,false,finally,for,from,function,get,if,implements,import,in,infer,instanceof,interface,'
    +'keyof,let,namespace,new,null,of,private,protected,public,readonly,return,satisfies,set,static,super,'
    +'switch,this,throw,true,try,type,typeof,undefined,var,void,while,with,yield',
  py:'and,as,assert,async,await,break,case,class,continue,def,del,elif,else,except,finally,for,from,global,'
    +'if,import,in,is,lambda,match,nonlocal,not,or,pass,raise,return,self,try,while,with,yield,True,False,None',
  sh:'if,then,else,elif,fi,for,while,until,do,done,case,esac,in,function,return,local,export,readonly,'
    +'declare,source,shift,exit,set,unset,trap,eval,echo,cd,test,read,printf,alias',
  go:'break,case,chan,const,continue,default,defer,else,fallthrough,for,func,go,goto,if,impl,import,interface,'
    +'let,map,match,mod,mut,package,pub,range,return,select,struct,switch,trait,type,unsafe,use,var,where,'
    +'nil,true,false,make,new,len,cap,append,string,int,bool,error',
  c:'auto,bool,break,case,char,class,const,constexpr,continue,default,delete,do,double,else,enum,extern,'
   +'false,float,for,goto,if,inline,int,long,namespace,new,nullptr,operator,override,private,protected,public,'
   +'register,return,short,signed,sizeof,static,struct,switch,template,this,true,typedef,typename,union,'
   +'unsigned,using,virtual,void,volatile,while',
  rb:'alias,and,begin,break,case,class,def,defined?,do,else,elsif,end,ensure,false,for,if,in,module,next,nil,'
    +'not,or,redo,rescue,retry,return,self,super,then,true,undef,unless,until,when,while,yield,require,attr',
  // no keywords below is correct — strings, numbers and comments suffice; forced keywords only create false hits
  xml:'', json:'', yaml:'', css:'', props:'', g4:'',
  none:'',      // prose/records (md/txt/log/diff) — correctly no keywords to color
};
for(const k in LKW) LKW[k] = new Set(LKW[k] ? LKW[k].split(',') : []);
// SQL is case-insensitive (select and SELECT are both keywords)
const KWFOLD = {sql:1};

const KW = new Set(('abstract,as,assert,async,await,base,bool,boolean,break,byte,case,catch,char,class,'
 +'const,continue,def,default,delete,do,double,elif,else,enum,except,export,extends,false,final,finally,'
 +'float,fn,for,from,func,function,go,goto,if,impl,implements,import,in,instanceof,int,interface,is,let,'
 +'lambda,long,match,mod,module,mut,new,nil,none,not,null,or,and,package,pass,private,protected,public,'
 +'raise,record,return,select,self,short,static,struct,super,switch,synchronized,this,throw,throws,trait,'
 +'true,try,type,typeof,union,use,using,var,void,when,where,while,with,yield,'
 +'SELECT,FROM,WHERE,JOIN,LEFT,RIGHT,INNER,OUTER,ON,GROUP,ORDER,BY,HAVING,LIMIT,OFFSET,INSERT,INTO,'
 +'VALUES,UPDATE,SET,DELETE,CREATE,ALTER,DROP,TABLE,INDEX,VIEW,AND,OR,NOT,NULL,AS,DISTINCT,COUNT,'
 +'echo,cd,export,sudo,grep,awk,sed,curl,git,npm,node,python3,pip').split(','));

function hl(src, lang){
  // Token order is priority: comment → string → annotation → number → identifier.
  // Identifiers are classified by what follows (by **shape**, not a parser):
  //   ident(  → method · capitalized → type/class · ALL_CAPS → constant · this.x/$x → field
  const RE = /(\/\/[^\n]*|#[^\n]*|--[^\n]*|\/\*[\s\S]*?\*\/)|('(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"|`(?:[^`\\]|\\.)*`)|(@[A-Za-z_][A-Za-z0-9_]*)|(\b\d[\d_.]*(?:[eE][-+]?\d+)?[fFdDlL]?\b|\b0[xX][0-9a-fA-F_]+\b)|([A-Za-z_$][A-Za-z0-9_$]*)/g;
  const kw = (lang && LKW[lang]) ? LKW[lang] : KW;
  const fold = !!(lang && KWFOLD[lang]);
  let out = '', last = 0, m;
  while((m = RE.exec(src)) !== null){
    out += esc(src.slice(last, m.index));
    const t = m[0];
    const after = src.slice(m.index + t.length);
    const before = src.slice(0, m.index);
    if(m[1])      out += '<span class=cc>'+esc(t)+'</span>';          // comment
    else if(m[2]) out += '<span class=cs>'+esc(t)+'</span>';          // string
    else if(m[3]) out += '<span class=ca>'+esc(t)+'</span>';          // annotation @Xxx
    else if(m[4]) out += '<span class=cn>'+esc(t)+'</span>';          // number
    else if(kw.has(fold ? t.toLowerCase() : t))
                                             out += '<span class=ck>'+esc(t)+'</span>';   // keyword
    else if(/^\s*\(/.test(after))            out += '<span class=cm>'+esc(t)+'</span>';   // method call/declaration
    else if(/^[A-Z][A-Z0-9_]*$/.test(t) && t.length > 1)
                                             out += '<span class=cf>'+esc(t)+'</span>';   // constant ALL_CAPS
    else if(/^[A-Z]/.test(t))                out += '<span class=ct>'+esc(t)+'</span>';   // type/class
    else if(/(this|self)\.$/.test(before) || t[0] === '$')
                                             out += '<span class=cf>'+esc(t)+'</span>';   // field
    else out += esc(t);
    last = m.index + t.length;
  }
  return out + esc(src.slice(last));
}
function codeBlock(body, lang){
  const tag = lang ? '<span class=cl>'+esc(lang)+'</span>' : '';
  return '<pre class=cb>'+tag+'<code>'+hl(body, lang)+'</code></pre>';
}

// Source viewer preview only (doc=1): http(s) links, relative links as data-mdrel, images as text. ⚠Links stay out of <code>.
// ⚠One pass: a code span outside link text is kept whole; link text may hold code spans ([`x.md`](x.md)), the URL never does.
function mdLinks(h){
  return h.replace(/(<code>[\s\S]*?<\/code>)|(!?)\[((?:<code>[^<]*<\/code>|(?!<code>)[^\]])*)\]\(((?:(?!<code>)[^()\s])+)\)/g, (m, c, img, t, u) => {
    if(c) return c;
    if(img && !/^[a-z][a-z0-9+.\-]*:/i.test(u) && !/^\//.test(u) && !/[\x00-\x1f]/.test(u)
       && /\.(png|jpe?g|gif|webp|svg)$/i.test(u.split(/[#?]/)[0]))   // R1: relative image, hydrated by 81d strMdImgs
      return '<span class=mdimg data-mdimg="' + u + '">' + (t || u) + '</span>';
    if(img) return '<span class=mdimg>' + (t || u) + '</span>';                    // ⚠no remote images
    if(/^https?:\/\/[^\x00-\x20]+$/i.test(u)) return '<a href="' + u + '" target=_blank rel="noopener noreferrer">' + t + '</a>';
    if(/^[a-z][a-z0-9+.\-]*:/i.test(u) || /^\/\//.test(u) || /[\x00-\x1f]/.test(u)) return m;   // javascript:, data:, //host
    return '<a class=mdrel data-mdrel="' + u + '">' + t + '</a>';
  });
}
// ⚠md(src) without doc must stay byte-identical — chat, digest and work log use it (tests/test_structure_follow_js.py pins it).
// ln (split view only): an empty <i class=mdln data-ln=<1-based line>> precedes each top-level block for scroll sync (81c strMdSync).
// ⚠A separate marker, not an attribute on the block — tests pin the block tags byte-for-byte.
function md(src, doc, ln){
  const out=[], lines=String(src).split(NL); let i=0, fence=false, buf=[], list=false, lang='', f0=0;
  const put=(s, n)=>out.push(ln ? '<i class=mdln data-ln="'+(n+1)+'"></i>'+s : s);
  const inline_ = doc ? (x => mdLinks(inline(x))) : inline;
  const fb = doc ? ((b, lg) => lg.toLowerCase() === 'mermaid' && typeof mmdBlock === 'function' ? mmdBlock(b) : codeBlock(b, lg)) : codeBlock;   // 81e draws mermaid
  const cl=()=>{ if(list){ out.push('</ul>'); list=false; } };
  while(i<lines.length){
    const l=lines[i];
    if(fence){ if(/^\s*```/.test(l)){ put(fb(buf.join(NL), lang), f0); fence=false; buf=[]; lang=''; } else buf.push(l); i++; continue; }
    if(/^\s*```/.test(l)){ cl(); fence=true; f0=i; lang=(l.trim().slice(3).trim().split(/\s+/)[0]||'').slice(0,12); i++; continue; }
    if(/^\s*\|/.test(l) && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i+1]||'')){
      cl(); const t0=i, cells=r=>r.trim().replace(/^\||\|$/g,'').split('|').map(c=>inline_(c.trim()));
      let t='<table><thead><tr>'+cells(l).map(c=>'<th>'+c+'</th>').join('')+'</tr></thead><tbody>'; i+=2;
      while(i<lines.length && /^\s*\|/.test(lines[i])){ t+='<tr>'+cells(lines[i]).map(c=>'<td>'+c+'</td>').join('')+'</tr>'; i++; }
      put(t+'</tbody></table>', t0); continue;
    }
    let m=l.match(/^(#{1,6})\s+(.*)$/); if(m){ cl(); put(doc ? '<h'+m[1].length+'>'+inline_(m[2])+'</h'+m[1].length+'>' : '<h3>'+inline(m[2])+'</h3>', i); i++; continue; }
    if(/^\s*(---|___|\*\*\*)\s*$/.test(l)){ cl(); put('<hr>', i); i++; continue; }
    // Consecutive `>` lines = one blockquote, body rendered recursively (nesting works).
    if(/^\s*>/.test(l)){ cl(); const q=[], q0=i; while(i<lines.length && /^\s*>/.test(lines[i])){ q.push(lines[i].replace(/^\s*> ?/, '')); i++; }
      put('<blockquote>'+md(q.join(NL), doc)+'</blockquote>', q0); continue; }
    m=l.match(/^\s*(?:[-*·•]|\d+\.)\s+(.*)$/);
    if(m){ if(!list){ put('<ul>', i); list=true; }
      const tk=m[1].match(/^\[([ xX])\]\s+(.*)$/);   // GFM task item: read-only box (disabled, nothing is sent)
      out.push(tk ? '<li class=mdtask><input type=checkbox disabled'+(tk[1]===' ' ? '' : ' checked')+'> '+inline_(tk[2])+'</li>' : '<li>'+inline_(m[1])+'</li>'); i++; continue; }
    if(!l.trim()){ cl(); i++; continue; }
    cl(); put('<p>'+inline_(l)+'</p>', i); i++;
  }
  if(fence) put(fb(buf.join(NL), lang), f0);   // unclosed fences are emitted as code too
  cl(); return out.join('');
}
// Wire values from mailbox post titles (Korean tags), not UI.
const KIND=[[/의논|질문|확인\s*요청|요청|제안|검토/,'ask'],[/^답|답변|반영완료|동의|수용/,'ans'],[/정정|취소|철회|오류/,'fix']];
// ★Closing tags are matched **exactly** (same set as mailbox_core.CLOSE_TAGS) — if a word like «applied/done» in a title
//   is mistaken for closing, nudging turns off and a post needing an answer gets silently buried.
const DONE=new Set(['마침','종결','완료','DONE','CLOSED']);
function kindOf(s){ const m=String(s||'').match(/^\s*\[([^\]]{1,20})\]/); if(!m) return null;
  const tag=m[1].trim();
  if(DONE.has(tag.toUpperCase())||DONE.has(tag)) return {tag:tag,cls:'done'};
  for(const k of KIND) if(k[0].test(tag)) return {tag:tag,cls:k[1]}; return {tag:tag,cls:'note'}; }
// Is the thread closed — closed if **the last post** is a closing one (reopens automatically on a new post).
const closedT=items=>{ const l=items[items.length-1]; return !!(l&&l.kind&&l.kind.cls==='done'); };
const stripTag=s=>String(s||'').replace(/^\s*\[[^\]]{1,20}\]\s*/,'');
const day=t=>new Date(t/1e6).toLocaleDateString(LOC(),{month:'long',day:'numeric',weekday:'short'});
const hm=t=>new Date(t/1e6).toLocaleTimeString(LOC(),{hour:'2-digit',minute:'2-digit'});
// Name disambiguation — names **sharing a prefix** like `advocate`/`agent` can't be told apart by one letter and one color.
//   (1) two-letter initials (Ad/Ag)  (2) color from a hash of the full name, nudged away if close to a color already used.
// Prefixes come from /api/state.cfg.stripPrefixes (install config); default strips nothing.
let STRIP_PREFIXES=[];
const nmKey=w=>{let s=String(w); for(const p of STRIP_PREFIXES){ if(p&&s.startsWith(p)){ s=s.slice(p.length); break; } } return s.trim()||'?';};
const ini=w=>{const s=nmKey(w); return (s[0]||'?').toUpperCase()+(s[1]||'').toLowerCase();};
const HUES={};
function hueOf(w){
  const s=nmKey(w).toLowerCase();
  if(HUES[s]!==undefined) return HUES[s];
  let h=0; for(const c of s) h=(h*31+c.charCodeAt(0))%360;
  const used=Object.values(HUES);
  for(let i=0;i<36;i++){                          // rotate by 10 degrees to keep at least 40 degrees from the nearest color
    const cand=(h+i*10)%360;
    if(used.every(u=>{const d=Math.abs(u-cand); return Math.min(d,360-d)>=40;})){h=cand;break;}
  }
  return HUES[s]=h;
}
const avSty=w=>' style="background:hsl('+hueOf(w)+' 40% 21%);color:hsl('+hueOf(w)+' 72% 74%)"';
const nmSty=w=>' style="color:hsl('+hueOf(w)+thc(' 72% 74%',' 72% 25%')+')"';   // ⚠light 25%: lowest lightness where all 360 hues reach 4.5:1 on #eceef2 (hover)

// ★Is this document **the diff popup window**. Same HTML/JS reused; in the popup the main view is hidden and
//   only the diff shows full screen (why not two copies: the diff renderer and CSS are reused as-is).
const DPOP_CWD = new URLSearchParams(location.search).get('cwd') || '';
const ISPOP = location.pathname === '/diff' && !!DPOP_CWD;
// Same document again for the work-log popup (/work?cwd&tid) and the branch file-diff popup (/brdiff?repo&sha&path).
const WPQ = new URLSearchParams(location.search);
const ISWP = location.pathname === '/work' && !!(WPQ.get('cwd') && WPQ.get('tid'));
const ISBP = location.pathname === '/brdiff' && !!(WPQ.get('repo') && WPQ.get('sha') && WPQ.get('path'));
let MSGS=[], CUR={}, ROOMS={}, PROF={}, MINE=[], PRES={}, ACK={}, SESS=[], since=0;
let ARCHRUN = {}, SECRUN = {}, SIDEREUS_DIR = '';   // state `archRun` (84j, 48h) · `secRun` (84l) · `codeDir` = the Sidereus repo holding its tool pipelines
let PLREQ = {};   // state `plReq`: pipeline request records per repo (84l2 archReqRows)
let PROJ_GONE = new Set();   // state `projGone`: session folders deleted from disk (80 strProjList skips them)
// ⚠Empty `SESS` before the first /api/state is "not loaded", not "none" — views must show loading until this flips.
let STATE_IN = false;
let ACKSINCE=0;                      // acks for posts older than this are not sent by the server (receipt wording differs)
let USG = null;      // last usage (the 5h limit is needed to draw the live chart's reference line)
// ★Invite selection lives **outside the DOM** — the list redraws every 2.5s, so checkbox state in the DOM would vanish.
const picked = new Set();      // set of mailbox ids
let diffOpen = '';             // cwd of the session this popup is viewing (one window = one diff)
let diffRepo = '';             // repo being viewed now — one session can touch several repos
let diffData = null;           // that response — survives polling re-renders
let inviteRoom = '';           // room name being typed (survives re-renders)
// ★Place (room) and filter are **separate** (2026-08-26). Filters, rooms and threads used to share one tab row, so
//   "awaiting reply in room-A" was impossible (both were tabs, only one could be on). A few more rooms and nothing could be found.
//   A room is **a place, not a filter** — own row, and filters apply only within the chosen place.
// ★Middle-column mode (2026-08-27) — when chat is unused it serves as **the work-log console**.
//   A modal blocks everything else when open, unfit for "keep watching". The choice is remembered in the browser.
// ★**New-post count** on the chat tab (2026-09-02). Counts only posts arriving while viewing another tab —
//   my own posts are not counted (calling what I just sent 'new' would make the badge lie).
//   Baseline is right after loading: all old posts suddenly showing as 'new' would be meaningless.
let chatSeen = 0;
function chatNew(){
  if(!chatSeen) return 0;
  // ⚠Own posts by identity too, not only idSrc: `mine` now includes VIEWER_ME, and nothing here may count it as new
  const me = (typeof CFG !== 'undefined' && CFG && (CFG.viewerIds || [CFG.viewerMe])) || [];   // both default spellings when unset
  return (MSGS||[]).filter(m => (+m.t) > chatSeen && m.idSrc !== 'viewer' && !(m.from && me.includes(m.from))).length;
}
function chatMark(){
  const t = (MSGS||[]).reduce((a, m) => Math.max(a, +m.t || 0), 0);
  if(t) chatSeen = t;
}
