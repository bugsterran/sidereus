"""uiConfirm (web/js/08c-confirm.js): one native <dialog> confirm in a fake DOM.
R2: Tab/Shift+Tab stay on its two buttons, Esc = «Cancel» and stops propagation, page clicks are swallowed, focus returns to
the opener (re-found through cfgFocusSel when a repaint detached it). R3: title/body via textContent, ok label/danger,
CSS wraps and scrolls a long body and follows the --nx-* tokens."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import ROOT, js_all, js_fn
from tests._node import node_e

FNS = ("cfgFocusSel", "ucfEl", "uiConfirm", "ucfDone", "ucfKey", "ucfPtr")

# Minimal DOM: compound selectors (tag #id .class [attr] [attr="v"] :not([disabled])) joined by descendant spaces.
# ⚠A modal dialog makes everything outside it inert: focus() there is a no-op, so refocus-before-close would fail.
FAKE = r"""
function T(s){ return s; }
const ERRS = []; function softErr(t){ ERRS.push(t); }
const window = {ls: [], addEventListener(t, f, c){ this.ls.push([t, f.name, c === true]); }};
var document = null;
function cmp(el, s){
  if(!el || !el.tagName) return false;
  const en = /:not\(\[disabled\]\)/.test(s); s = s.replace(/:not\(\[disabled\]\)/g, '');
  if(en && el.hasAttribute('disabled')) return false;
  const m = /^([a-z]+)?((?:#[\w-]+|\.[\w-]+|\[[\w-]+(?:="[^"]*")?\])*)$/.exec(s);
  if(!m) throw new Error('fake selector: ' + s);
  if(m[1] && el.tagName !== m[1].toUpperCase()) return false;
  for(const t of m[2].match(/#[\w-]+|\.[\w-]+|\[[^\]]+\]/g) || []){
    if(t[0] === '#'){ if(el.id !== t.slice(1)) return false; }
    else if(t[0] === '.'){ if(!el.className.split(/\s+/).includes(t.slice(1))) return false; }
    else { const a = /^\[([\w-]+)(?:="([^"]*)")?\]$/.exec(t); if(!el.hasAttribute(a[1]) || (a[2] != null && el.getAttribute(a[1]) !== a[2])) return false; }
  }
  return true;
}
function match(el, sel){
  const ps = sel.trim().split(/\s+/);
  if(!cmp(el, ps.pop())) return false;
  let n = el.parentNode;
  while(ps.length && n){ if(cmp(n, ps[ps.length - 1])) ps.pop(); n = n.parentNode; }
  return !ps.length;
}
class El {
  constructor(tag){ this.tagName = tag.toUpperCase(); this.attrs = {}; this.kids = []; this.parentNode = null; this._t = ''; this.hidden = false; this.ls = {}; }
  get id(){ return this.attrs.id || ''; } set id(v){ this.attrs.id = String(v); }
  get className(){ return this.attrs['class'] || ''; } set className(v){ this.attrs['class'] = String(v); }
  get classList(){ const me = this; return {
    toggle(c, on){ const s = new Set(me.className.split(/\s+/).filter(Boolean)); if(on === undefined) on = !s.has(c); if(on) s.add(c); else s.delete(c); me.className = [...s].join(' '); return on; },
    contains(c){ return me.className.split(/\s+/).includes(c); } }; }
  setAttribute(k, v){ this.attrs[k] = String(v); } getAttribute(k){ return k in this.attrs ? this.attrs[k] : null; }
  hasAttribute(k){ return k in this.attrs; } removeAttribute(k){ delete this.attrs[k]; }
  // Layout exists only while a modal is shown: an `over` element reports overflow then, 0 before showModal.
  get scrollHeight(){ return this.over && document._modal ? 500 : 0; } get clientHeight(){ return this.over && document._modal ? 100 : 0; }
  get dataset(){ const o = {}; for(const k in this.attrs) if(k.startsWith('data-')) o[k.slice(5).replace(/-([a-z])/g, (m, c) => c.toUpperCase())] = this.attrs[k]; return o; }
  set type(v){ this.attrs.type = v; }
  appendChild(c){ if(c.parentNode) c.parentNode.removeChild(c); c.parentNode = this; this.kids.push(c); return c; }
  removeChild(c){ this.kids = this.kids.filter(x => x !== c); c.parentNode = null; return c; }
  remove(){ if(this.parentNode) this.parentNode.removeChild(this); }
  contains(x){ for(; x; x = x.parentNode) if(x === this) return true; return false; }
  get isConnected(){ let n = this; while(n.parentNode) n = n.parentNode; return n === document.documentElement; }
  get textContent(){ return this._t; } set textContent(v){ this._t = String(v); }
  set innerHTML(v){ throw new Error('innerHTML written'); }
  focus(){ if(!this.isConnected || (document._modal && !document._modal.contains(this))) return; document.activeElement = this; }
  all(){ const out = []; const w = n => n.kids.forEach(k => { out.push(k); w(k); }); w(this); return out; }
  querySelectorAll(s){ return this.all().filter(e => match(e, s)); }
  querySelector(s){ return this.querySelectorAll(s)[0] || null; }
  closest(s){ for(let n = this; n && n.tagName; n = n.parentNode) if(match(n, s)) return n; return null; }
  addEventListener(t, f){ (this.ls[t] = this.ls[t] || []).push(f); }
  fire(t, e){ (this.ls[t] || []).forEach(f => f(e)); }
}
class Dlg extends El {
  constructor(){ super('dialog'); this.open = false; }
  showModal(){ if(!this.isConnected) throw new Error('not connected'); this.open = true; document._modal = this; }
  close(){ this.open = false; if(document._modal === this) document._modal = null; }
}
function newDoc(){
  const html = new El('html'), body = new El('body');
  document = {documentElement: html, body, activeElement: body, _modal: null,
    createElement: t => t === 'dialog' ? new Dlg() : new El(t),
    getElementById: id => html.all().find(e => e.id === id) || null,
    querySelector: s => html.querySelector(s), querySelectorAll: s => html.querySelectorAll(s)};
  html.appendChild(body);
  UCF = null;
  return document;
}
function ev(o){ return Object.assign({pd: false, sp: false, sip: false, preventDefault(){ this.pd = true; },
  stopPropagation(){ this.sp = true; }, stopImmediatePropagation(){ this.sip = true; this.sp = true; }}, o); }
function btn(attrs){ const b = new El('button'); for(const k in attrs) b.setAttribute(k, attrs[k]); return b; }
const tick = () => new Promise(r => setTimeout(r, 0));
"""


def _run(body):
    src = js_all()
    let_ucf = re.search(r"^let UCF\b.*$", src, re.M).group(0)
    reg = re.search(r"^if\(typeof window !== 'undefined' && window\.addEventListener\)\{\n  window\.addEventListener\('keydown', ucfKey.*?^}",
                    src, re.M | re.S).group(0)
    js = (let_ucf + "\n" + FAKE + "\n".join(js_fn(n) for n in FNS) + "\n" + reg + "\n"
          + "(async () => { const R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R)); })()"
            ".catch(e => { console.error(e.stack); process.exit(1); });")
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=30, encoding="utf-8")
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


SCENARIOS = r"""
// R2 open: dialog on <body>, labelled, initial focus «Cancel», default labels
{ const D = newDoc(), op = btn({'data-x': 'a'}); D.body.appendChild(op); op.focus();
  let got = null; const p = uiConfirm('Title', {body: 'line1\nline2'}); p.then(v => { got = v; });
  const d = D.getElementById('ucf'), bs = d.querySelectorAll('[data-ucf]');
  R.open = {parent: d.parentNode === D.body, open: d.open, cls: d.className, lab: d.getAttribute('aria-labelledby'),
    desc: d.getAttribute('aria-describedby'), focus: D.activeElement === bs[0], labels: bs.map(b => b.textContent),
    okcls: bs[1].className};
  // R2 Esc: preventDefault + stopImmediatePropagation, resolves false, focus back on the opener
  const e = ev({key: 'Escape', type: 'keydown'}); ucfKey(e); await p;
  R.esc = {got, pd: e.pd, sip: e.sip, open: d.open, back: D.activeElement === op}; }

// R2 ok click -> true; click event stopped; Enter keydown only stops propagation
{ const D = newDoc(); let got = null; const p = uiConfirm('T', {ok: 'Delete', danger: true}); p.then(v => { got = v; });
  const d = D.getElementById('ucf'), ok = d.querySelector('[data-ucf="1"]');
  const k = ev({key: 'Enter', type: 'keydown'}); ucfKey(k);
  const pd = ev({type: 'pointerdown', target: ok}); ucfPtr(pd);
  await tick(); const still = got === null && d.open;
  const c = ev({type: 'click', target: ok}); ucfPtr(c); await p;
  R.ok = {got, still, enter: [k.pd, k.sp], pdsp: pd.sp, csp: c.sp, label: ok.textContent, dng: ok.classList.contains('dng')}; }

// R2 backdrop click (target = the dialog) does nothing; native cancel = false
{ const D = newDoc(); let got = null; const p = uiConfirm('T'); p.then(v => { got = v; });
  const d = D.getElementById('ucf'), c = ev({type: 'click', target: d}); ucfPtr(c); await tick();
  const bd = {got, open: d.open, sp: c.sp};
  const ce = ev({type: 'cancel'}); d.fire('cancel', ce); await p;
  R.backdrop = bd; R.cancel = {got, pd: ce.pd, open: d.open}; }

// R2 Tab cycles inside: from ok -> Cancel, Shift+Tab from Cancel -> ok, from BODY -> Cancel
{ const D = newDoc(); const p = uiConfirm('T'); const d = D.getElementById('ucf'), bs = d.querySelectorAll('[data-ucf]');
  bs[1].focus(); const t1 = ev({key: 'Tab', type: 'keydown'}); ucfKey(t1); const a1 = D.activeElement === bs[0];
  const t2 = ev({key: 'Tab', shiftKey: true, type: 'keydown'}); ucfKey(t2); const a2 = D.activeElement === bs[1];
  const t3 = ev({key: 'Tab', type: 'keydown'}); ucfKey(t3); const a3 = D.activeElement === bs[0];
  D.activeElement = D.body; const t4 = ev({key: 'Tab', shiftKey: true, type: 'keydown'}); ucfKey(t4); const a4 = D.activeElement === bs[0];
  R.tab = {a1, a2, a3, a4, pd: [t1.pd, t2.pd, t3.pd, t4.pd], sp: [t1.sp, t2.sp]};
  ucfKey(ev({key: 'Escape'})); await p; }

// R2 a second call while open resolves false without opening; the first stays open
{ const D = newDoc(); let g1 = null; const p1 = uiConfirm('first'); p1.then(v => { g1 = v; });
  const g2 = await uiConfirm('second');
  const d = D.getElementById('ucf');
  R.busy = {g2, title: d.querySelector('.ucft').textContent, open: d.open, errs: ERRS.slice(), n: D.querySelectorAll('dialog').length};
  ucfKey(ev({key: 'Escape'})); await p1; }

// R2 opener detached by a repaint: re-found through cfgFocusSel selectors; a disabled twin is skipped
{ const D = newDoc(), box = new El('div'); D.body.appendChild(box);
  const op = btn({'data-mp': 'port'}); box.appendChild(op); op.focus();
  const p = uiConfirm('T', {body: 'x'});
  box.removeChild(op); const dis = btn({'data-mp': 'port', disabled: ''}); box.appendChild(dis);
  const twin = btn({'data-mp': 'port'}); box.appendChild(twin);
  ucfPtr(ev({type: 'click', target: D.querySelector('#ucf [data-ucf="0"]')})); const v = await p;
  R.refind = {v, twin: D.activeElement === twin, open: D.getElementById('ucf').open}; }

// R2 events while closed pass through untouched
{ newDoc(); const k = ev({key: 'Escape'}), c = ev({type: 'click', target: null}); ucfKey(k); ucfPtr(c);
  R.closed = {k: [k.pd, k.sp], c: c.sp}; }

// R3 title/body via textContent: markup stays literal (the fake throws on innerHTML); empty body hidden; reuse resets danger
{ const D = newDoc(); const p = uiConfirm('<b>t</b>', {body: '<i>/p/a</i>'}); const d = D.getElementById('ucf');
  const a = {title: d.querySelector('.ucft').textContent, body: d.querySelector('.ucfb').textContent, hidden: d.querySelector('.ucfb').hidden};
  ucfKey(ev({key: 'Escape'})); await p;
  const p2 = uiConfirm('again', {ok: 'Go'});
  const b = {hidden: d.querySelector('.ucfb').hidden, dng: d.querySelector('[data-ucf="1"]').classList.contains('dng'),
    n: D.querySelectorAll('dialog').length};
  ucfKey(ev({key: 'Escape'})); await p2;
  R.text = {a, b}; }

// R3: an overflowing body joins the Tab cycle (body, Cancel, ok); arrows on it only stop propagation (they scroll)
{ const D = newDoc(); ucfEl().querySelector('.ucfb').over = true;
  const p = uiConfirm('T', {body: 'a\nb\nc'}); const d = D.getElementById('ucf'), b = d.querySelector('.ucfb'), bs = d.querySelectorAll('[data-ucf]');
  const cyc = [D.activeElement === bs[0] ? 'cancel' : '?'], tab = sh => { ucfKey(ev({key: 'Tab', shiftKey: sh})); cyc.push(D.activeElement === b ? 'body' : D.activeElement === bs[0] ? 'cancel' : D.activeElement === bs[1] ? 'ok' : '?'); };
  tab(false); tab(false); tab(false); tab(true); tab(true);
  D.activeElement = D.body; tab(false);
  b.focus(); const k = ev({key: 'PageDown'}); ucfKey(k);
  R.over = {tabindex: b.getAttribute('tabindex'), cyc, pg: [k.pd, k.sp]};
  ucfKey(ev({key: 'Escape'})); await p;
  // same dialog, short body: tabindex dropped, two-button cycle
  b.over = false; const p2 = uiConfirm('T', {body: 'short'}); const cyc2 = [];
  for(let j = 0; j < 3; j++){ ucfKey(ev({key: 'Tab'})); cyc2.push(D.activeElement === bs[0] ? 'cancel' : D.activeElement === bs[1] ? 'ok' : '?'); }
  R.short = {tabindex: b.getAttribute('tabindex'), cyc: cyc2};
  ucfKey(ev({key: 'Escape'})); await p2; }

R.listeners = window.ls;
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class UiConfirm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = _run(SCENARIOS)

    def test_r2_opens_on_body_with_cancel_focused(self):
        o = self.R["open"]
        self.assertEqual(o, {"parent": True, "open": True, "cls": "ucf", "lab": "ucft", "desc": "ucfb", "focus": True,
                             "labels": ["Cancel", "Confirm"], "okcls": "wkrgb archok"})

    def test_r2_esc_cancels_and_stops_propagation(self):
        self.assertEqual(self.R["esc"], {"got": False, "pd": True, "sip": True, "open": False, "back": True})

    def test_r2_ok_click_true_and_page_clicks_swallowed(self):
        o = self.R["ok"]
        self.assertEqual(o, {"got": True, "still": True, "enter": [False, True], "pdsp": True, "csp": True,
                             "label": "Delete", "dng": True})

    def test_r2_backdrop_click_noop_native_cancel_false(self):
        self.assertEqual(self.R["backdrop"], {"got": None, "open": True, "sp": True})
        self.assertEqual(self.R["cancel"], {"got": False, "pd": True, "open": False})

    def test_r2_tab_cycles_between_buttons(self):
        self.assertEqual(self.R["tab"], {"a1": True, "a2": True, "a3": True, "a4": True,
                                         "pd": [True, True, True, True], "sp": [True, True]})

    def test_r2_second_call_while_open_is_false(self):
        self.assertEqual(self.R["busy"], {"g2": False, "title": "first", "open": True, "errs": ["ucf-busy"], "n": 1})

    def test_r2_detached_opener_refound(self):
        self.assertEqual(self.R["refind"], {"v": False, "twin": True, "open": False})

    def test_r2_closed_events_untouched(self):
        self.assertEqual(self.R["closed"], {"k": [False, False], "c": False})

    def test_r2_window_capture_listeners(self):
        ls = {(t, f, c) for t, f, c in self.R["listeners"]}
        want = {("keydown", "ucfKey", True)} | {(t, "ucfPtr", True) for t in
                                                ("pointerdown", "mousedown", "pointerup", "mouseup", "click", "auxclick")}
        self.assertEqual(ls, want)

    def test_r3_overflowing_body_in_tab_cycle(self):
        self.assertEqual(self.R["over"], {"tabindex": "0", "cyc": ["cancel", "ok", "body", "cancel", "body", "ok", "cancel"],
                                          "pg": [False, True]})

    def test_r3_short_body_two_button_cycle(self):
        self.assertEqual(self.R["short"], {"tabindex": None, "cyc": ["ok", "cancel", "ok"]})

    def test_r3_text_content_literal(self):
        self.assertEqual(self.R["text"], {"a": {"title": "<b>t</b>", "body": "<i>/p/a</i>", "hidden": False},
                                          "b": {"hidden": True, "dng": False, "n": 1}})


class ConfirmCss(unittest.TestCase):
    """R3: long body wraps/scrolls at 900 wide, colours from theme tokens, no 00-core twins."""
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "web", "css", "96c-confirm.css"), encoding="utf-8") as fh:
            cls.css = fh.read()

    def rule(self, sel):
        m = re.search(re.escape(sel) + r"\{([^}]*)\}", self.css)
        self.assertIsNotNone(m, sel)
        return m.group(1)

    def test_r3_body_wraps_and_scrolls(self):
        b = self.rule("html[data-ui] .ucf .ucfb")
        for d in ("white-space:pre-wrap", "overflow-wrap:anywhere", "overflow:auto", "max-height:calc(100vh - 220px)"):
            self.assertIn(d, b)
        self.assertIn("width:min(560px,calc(100vw - 32px))", self.rule("html[data-ui] .ucf"))

    def test_r3_theme_tokens_and_data_ui_scope(self):
        box = self.rule("html[data-ui] .ucf")
        for d in ("background:var(--nx-panel)", "color:var(--nx-t1)", "border:1px solid var(--nx-rule)"):
            self.assertIn(d, box)
        self.assertIn("background:var(--nx-err)", self.rule("html[data-ui][data-ui][data-ui] .ucf .wkrgb.archok.dng:not([disabled])"))
        sels = re.findall(r"(?:^|\})\s*([^{}/]+?)\{", re.sub(r"/\*.*?\*/", "", self.css, flags=re.S))
        self.assertTrue(sels)
        for s in sels:
            self.assertTrue(s.strip().startswith("html[data-ui]"), s)


if __name__ == "__main__":
    unittest.main()
