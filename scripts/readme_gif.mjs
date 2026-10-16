#!/usr/bin/env node
// Animated README hero from the synthetic `--demo` world: the Pipelines view with a change-flow run lighting its stages
// in sequence (Design -> Implement -> Verify -> Review, one loop-back from Review, then done). Node 22 built-ins only.
// Same isolation and framing as scripts/readme_shots.mjs (shared helpers: scripts/readme_cdp.mjs).
// ⚠Never points at the live viewer (8799) — every pixel must come from demo data.
//
//   node scripts/readme_gif.mjs                 write docs/images/hero-en.gif and hero-ko.gif
//   node scripts/readme_gif.mjs --frames DIR    also write a few composited frames as PNG to DIR (for a visual check)
//
// The demo has no live progression, so the script rewrites the web session's `plrun` (the server's merged run model)
// step by step in the page — on SESS for an immediate repaint and on every /api/state reply so a poll keeps the step.
// Frames: app viewport 1200x750 captured at device scale APP_DSF, composited in Node into the backdrop frame rendered once
// with a solid black and a solid white box (alpha = (white - black) / 255, so rounded corners and shadow stay exact),
// then one global 255-colour median-cut palette, per-frame changed-rectangle with transparency, LZW, NETSCAPE loop.
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import { ROOT, sleep, sandbox, CDP, openApp, frameHtml } from './readme_cdp.mjs';

const OUT = path.join(ROOT, 'docs', 'images');
const VW = 1200, VH = 750;                      // app viewport, same as readme_shots
const FW = 1280, FH = 800, IW = 1152, IH = 720; // frame page and inner box (css px), same as readme_shots
const SCALE = 0.875;                            // frame device scale ⇒ GIF 1120x700; offsets 56,35 stay integer
const APP_DSF = IW * SCALE / VW;                // 0.84 ⇒ app capture 1008x630 = inner box in device px
const STEP_MS = 1100, HOLD_MS = 2000, FRAME_MS = 100;
const DEADLINE_MS = 240000;
const { cleanup, startDemo, startChrome } = sandbox('readme-gif');

// ---- page side: run steps -------------------------------------------------------
// Each step: current minute `c` on a run timeline (minutes) and per-stage [outcome, start, end?, extra].
// Stage keys are the demo file's titles (sidereus/demo_tools.py); the page translates them per language.
const STEPS = [
  { c: 6,  s: { '설계': ['run', 0] } },
  { c: 22, s: { '설계': ['done', 0, 14], '구현': ['run', 15] } },
  { c: 44, s: { '설계': ['done', 0, 14], '구현': ['done', 15, 38], '검증': ['run', 39] } },
  { c: 55, s: { '설계': ['done', 0, 14], '구현': ['done', 15, 38], '검증': ['done', 39, 50], '리뷰': ['run', 51] } },
  { c: 64, s: { '설계': ['done', 0, 14], '구현': ['run', 15, null, { p0: 61, k: 2, from: { '리뷰': 1 }, ps: [[15, 38, 'back']] }],
               '검증': ['done', 39, 50], '리뷰': ['back', 51, 60] } },
  { c: 80, s: { '설계': ['done', 0, 14], '구현': ['done', 15, 74, { p0: 61, k: 2, from: { '리뷰': 1 }, ps: [[15, 38, 'back']] }],
               '검증': ['run', 39, null, { p0: 75, k: 2, ps: [[39, 50, 'done']] }], '리뷰': ['back', 51, 60] } },
  { c: 92, s: { '설계': ['done', 0, 14], '구현': ['done', 15, 74, { p0: 61, k: 2, from: { '리뷰': 1 }, ps: [[15, 38, 'back']] }],
               '검증': ['done', 39, 86, { p0: 75, k: 2, ps: [[39, 50, 'done']] }], '리뷰': ['run', 51, null, { p0: 87, k: 2, ps: [[51, 60, 'back']] }] } },
  { c: 97, end: true, s: { '설계': ['done', 0, 14], '구현': ['done', 15, 74, { p0: 61, k: 2, from: { '리뷰': 1 }, ps: [[15, 38, 'back']] }],
               '검증': ['done', 39, 86, { p0: 75, k: 2, ps: [[39, 50, 'done']] }], '리뷰': ['done', 51, 95, { p0: 87, k: 2, ps: [[51, 60, 'back']] }] } },
];
const LABS = { '설계': 'Plan: Checkout validation spec', '구현': 'general-purpose: Form validation rules',
  '검증': 'general-purpose: Run gates and screen check', '리뷰': 'code-reviewer: Review the diff' };

// Rewrites the change-flow plrun of whichever session carries it; `window.__gifStep` holds the active step.
const BOOT = `(() => {
  const LABS = ${JSON.stringify(LABS)};
  window.__gifMut = sessions => {
    const st = window.__gifStep; if (!st) return;
    const now = Date.now() / 1000, t = m => now - (st.c - m) * 60;
    // The «Running» strip lists Workflow runs (x.wf) and [pl:]-tagged sessions, not plrun: drop the static Workflow run and
    // tag the plrun session (main-agent marker x.plm) so the strip shows this same run. Kept on the last stage at the end
    // (with end = 0) so the strip does not vanish and shift the canvas up.
    (sessions || []).forEach(x => { if (x) x.wf = []; });
    (sessions || []).forEach(x => (x.plrun || []).forEach(r => {
      if (r.name !== 'change-flow') return;
      const S = {}, aid = r.__aid || (r.__aid = {});
      Object.keys(st.s).forEach(k => {
        const [o, a, b, ex] = st.s[k], e = ex || {}, run = o === 'run', t1 = run ? now : t(b);
        const v = { o, n: 1, t0: t(a), t1, from: e.from || {} };
        if (e.p0 != null) { v.p0 = t(e.p0); v.k = e.k; }
        if (e.ps) v.ps = e.ps.map(p => ({ a: t(p[0]), b: t(p[1]), s: p[2] }));
        v.ag = [{ aid: aid[k] || (aid[k] = 'a' + Math.random().toString(16).slice(2, 18)), tid: 'toolu_gif', lab: LABS[k],
                  run, t0: e.p0 != null ? t(e.p0) : t(a), t1 }];
        S[k] = v;
      });
      const live = Object.keys(S).filter(k => S[k].o === 'run');
      x.plm = { name: 'change-flow', title: live[0] || '리뷰' };
      r.stages = S; r.cur = live[0] || '리뷰'; r.t0 = t(0); r.t1 = st.end ? t(st.c - 2) : now;
      r.end = 0;   // ⚠a set end drops the plm tag (plTagNames), so the strip row would vanish on the last step
    }));
  };
  const f = window.fetch;
  window.fetch = function (a, o) {
    const p = f.apply(this, arguments);
    if (String(a).indexOf('/api/state') < 0 || !window.__gifStep) return p;
    return p.then(r => r.clone().json().then(j => { window.__gifMut(j.sessions); return new Response(JSON.stringify(j), { status: r.status, headers: r.headers }); }, () => r));
  };
})();`;

// ---- PNG -------------------------------------------------------------------------
function pngDecode(buf) {
  let p = 8, w = 0, h = 0, ct = 0, idat = [];
  while (p < buf.length) {
    const len = buf.readUInt32BE(p), type = buf.toString('latin1', p + 4, p + 8), d = buf.subarray(p + 8, p + 8 + len);
    if (type === 'IHDR') {
      w = d.readUInt32BE(0); h = d.readUInt32BE(4); ct = d[9];
      if (d[8] !== 8 || (ct !== 2 && ct !== 6) || d[12] !== 0) throw new Error('png: only 8-bit RGB/RGBA non-interlaced');
    } else if (type === 'IDAT') idat.push(d);
    else if (type === 'IEND') break;
    p += 12 + len;
  }
  const raw = zlib.inflateSync(Buffer.concat(idat)), bpp = ct === 6 ? 4 : 3, stride = w * bpp;
  const rgb = new Uint8Array(w * h * 3), cur = new Uint8Array(stride), prev = new Uint8Array(stride);
  for (let y = 0, q = 0; y < h; y++) {
    const ft = raw[q++];
    for (let i = 0; i < stride; i++, q++) {
      const x = raw[q], a = i >= bpp ? cur[i - bpp] : 0, b = prev[i], c = i >= bpp ? prev[i - bpp] : 0;
      let v;
      if (ft === 0) v = x; else if (ft === 1) v = x + a; else if (ft === 2) v = x + b; else if (ft === 3) v = x + ((a + b) >> 1);
      else { const pp = a + b - c, pa = Math.abs(pp - a), pb = Math.abs(pp - b), pc = Math.abs(pp - c); v = x + (pa <= pb && pa <= pc ? a : pb <= pc ? b : c); }
      cur[i] = v & 255;
    }
    for (let x = 0; x < w; x++) { const o = (y * w + x) * 3; rgb[o] = cur[x * bpp]; rgb[o + 1] = cur[x * bpp + 1]; rgb[o + 2] = cur[x * bpp + 2]; }
    prev.set(cur);
  }
  return { w, h, rgb };
}
function pngEncode(w, h, rgb) {
  const raw = Buffer.alloc((w * 3 + 1) * h);
  for (let y = 0; y < h; y++) Buffer.from(rgb.buffer, rgb.byteOffset + y * w * 3, w * 3).copy(raw, y * (w * 3 + 1) + 1);
  const chunk = (t, d) => { const l = Buffer.alloc(4); l.writeUInt32BE(d.length); const td = Buffer.concat([Buffer.from(t, 'latin1'), d]);
    const c = Buffer.alloc(4); c.writeUInt32BE(zlib.crc32(td)); return Buffer.concat([l, td, c]); };
  const ih = Buffer.alloc(13); ih.writeUInt32BE(w, 0); ih.writeUInt32BE(h, 4); ih[8] = 8; ih[9] = 2;
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ih), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}

// ---- palette: median cut over a 6-bit-per-channel histogram ------------------------------
const key6 = (r, g, b) => ((r >> 2) << 12) | ((g >> 2) << 6) | (b >> 2);
function medianCut(hist, n) {
  const cols = [];
  for (let k = 0; k < hist.length; k++) if (hist[k]) cols.push(k);
  const ch = (k, c) => (k >> (12 - 6 * c)) & 63;
  const box = list => {
    const lo = [63, 63, 63], hi = [0, 0, 0]; let cnt = 0;
    for (const k of list) { cnt += hist[k]; for (let c = 0; c < 3; c++) { const v = ch(k, c); if (v < lo[c]) lo[c] = v; if (v > hi[c]) hi[c] = v; } }
    const r = [hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]], ax = r[0] >= r[1] && r[0] >= r[2] ? 0 : r[1] >= r[2] ? 1 : 2;
    return { list, cnt, ax, span: r[ax] };
  };
  const boxes = [box(cols)];
  while (boxes.length < n) {
    // Split the box with the most pixels × widest span, at its pixel-weighted median along that axis.
    let bi = -1, best = 0;
    boxes.forEach((b, i) => { const s = b.span > 0 && b.list.length > 1 ? Math.sqrt(b.cnt) * b.span : 0; if (s > best) { best = s; bi = i; } });
    if (bi < 0) break;
    const b = boxes[bi], l = b.list.slice().sort((x, y) => ch(x, b.ax) - ch(y, b.ax));
    let acc = 0, m = 0;
    for (; m < l.length - 1; m++) { acc += hist[l[m]]; if (acc * 2 >= b.cnt) break; }
    boxes.splice(bi, 1, box(l.slice(0, m + 1)), box(l.slice(m + 1)));
  }
  return boxes.map(b => {
    let r = 0, g = 0, bl = 0;
    for (const k of b.list) { const c = hist[k]; r += ch(k, 0) * c; g += ch(k, 1) * c; bl += ch(k, 2) * c; }
    const f = v => Math.min(255, Math.round(v / b.cnt * 4 + 2));
    return [f(r), f(g), f(bl)];
  });
}
function mapper(pal) {
  const lut = new Int16Array(1 << 18).fill(-1);
  return k => {
    let v = lut[k];
    if (v >= 0) return v;
    const r = ((k >> 12) << 2) + 2, g = (((k >> 6) & 63) << 2) + 2, b = ((k & 63) << 2) + 2;
    let bd = 1e9;
    for (let i = 0; i < pal.length; i++) { const p = pal[i], d = (p[0] - r) ** 2 * 3 + (p[1] - g) ** 2 * 4 + (p[2] - b) ** 2 * 2; if (d < bd) { bd = d; v = i; } }
    lut[k] = v; return v;
  };
}

// ---- GIF89a -----------------------------------------------------------------------
function lzw(idx, minBits) {
  const clear = 1 << minBits, eoi = clear + 1, out = [];
  let bits = minBits + 1, next = eoi + 1, acc = 0, nacc = 0;
  const put = c => { acc |= c << nacc; nacc += bits; while (nacc >= 8) { out.push(acc & 255); acc >>>= 8; nacc -= 8; } };
  // Dictionary: (prefix code, byte) -> code, generation-stamped so a reset costs nothing.
  const tab = new Int16Array(4096 * 256), gen = new Uint16Array(4096 * 256); let g = 1;
  put(clear);
  let pre = idx[0];
  for (let i = 1; i < idx.length; i++) {
    const c = idx[i], h = pre * 256 + c;
    if (gen[h] === g) { pre = tab[h]; continue; }
    put(pre);
    if (next < 4096) { tab[h] = next; gen[h] = g; if (next === (1 << bits) && bits < 12) bits++; next++; }
    else { put(clear); g++; bits = minBits + 1; next = eoi + 1; }
    pre = c;
  }
  put(pre); put(eoi);
  if (nacc > 0) out.push(acc & 255);
  const blocks = [Buffer.from([minBits])];
  const data = Buffer.from(out);
  for (let p = 0; p < data.length; p += 255) { const s = data.subarray(p, p + 255); blocks.push(Buffer.from([s.length]), s); }
  blocks.push(Buffer.from([0]));
  return Buffer.concat(blocks);
}
function gifEncode(w, h, pal, frames) {
  // pal: 255 colours + index 255 transparent. frames: [{idx: Uint8Array(w*h), cs}] (palette indices of the full frame).
  const T = 255, parts = [];
  const u16 = v => [v & 255, v >> 8];
  const gct = Buffer.alloc(256 * 3); pal.forEach((c, i) => { gct[i * 3] = c[0]; gct[i * 3 + 1] = c[1]; gct[i * 3 + 2] = c[2]; });
  parts.push(Buffer.from('GIF89a', 'latin1'), Buffer.from([...u16(w), ...u16(h), 0xF7, 0, 0]), gct);
  parts.push(Buffer.from([0x21, 0xFF, 11]), Buffer.from('NETSCAPE2.0', 'latin1'), Buffer.from([3, 1, 0, 0, 0]));   // loop forever
  let prev = null;
  for (const f of frames) {
    let x0 = 0, y0 = 0, x1 = w - 1, y1 = h - 1;
    if (prev) {   // changed rectangle; caller already merged identical frames
      x0 = w; y0 = h; x1 = -1; y1 = -1;
      for (let y = 0; y < h; y++) for (let x = 0, o = y * w; x < w; x++, o++) if (f.idx[o] !== prev[o]) {
        if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
      }
      if (x1 < 0) { x0 = y0 = x1 = y1 = 0; }
    }
    const rw = x1 - x0 + 1, rh = y1 - y0 + 1, sub = new Uint8Array(rw * rh);
    for (let y = 0; y < rh; y++) for (let x = 0; x < rw; x++) {
      const o = (y0 + y) * w + x0 + x, v = f.idx[o];
      sub[y * rw + x] = prev && v === prev[o] ? T : v;
    }
    // GCE: disposal 1 (keep), transparent index 255.
    parts.push(Buffer.from([0x21, 0xF9, 4, (1 << 2) | 1, ...u16(f.cs), T, 0]));
    parts.push(Buffer.from([0x2C, ...u16(x0), ...u16(y0), ...u16(rw), ...u16(rh), 0]), lzw(sub, 8));
    prev = f.idx;
  }
  parts.push(Buffer.from([0x3B]));
  return Buffer.concat(parts);
}

// ---- capture -------------------------------------------------------------------------
async function backdrop(cdp, base) {
  // Same tab type as a shot, but only the frame page: black and white inner box ⇒ background + alpha mask.
  const { browserContextId } = await cdp.send('Target.createBrowserContext', { disposeOnDetach: true });
  const { targetId } = await cdp.send('Target.createTarget', { url: 'about:blank', browserContextId });
  const { sessionId: sid } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
  const S = (m, p) => cdp.send(m, p, sid);
  await S('Page.enable');
  await S('Emulation.setDeviceMetricsOverride', { width: FW, height: FH, deviceScaleFactor: SCALE, mobile: false });
  const { frameTree } = await S('Page.getFrameTree');
  const shotOf = async col => {
    await S('Page.setDocumentContent', { frameId: frameTree.frame.id, html: frameHtml(FW, FH, IW, IH, '<div id=s style="background:' + col + '"></div>') });
    await sleep(150);
    return pngDecode(Buffer.from((await S('Page.captureScreenshot', { format: 'png' })).data, 'base64'));
  };
  const blk = await shotOf('#000'), wht = await shotOf('#fff');
  await cdp.send('Target.closeTarget', { targetId }).catch(() => {});
  await cdp.send('Target.disposeBrowserContext', { browserContextId }).catch(() => {});
  const n = blk.w * blk.h, alpha = new Float32Array(n);
  for (let i = 0; i < n; i++) alpha[i] = Math.max(0, Math.min(1, ((wht.rgb[i * 3] - blk.rgb[i * 3]) + (wht.rgb[i * 3 + 1] - blk.rgb[i * 3 + 1]) + (wht.rgb[i * 3 + 2] - blk.rgb[i * 3 + 2])) / 765));
  return { w: blk.w, h: blk.h, bg: blk.rgb, alpha };
}
function composite(bd, app) {
  const ox = Math.round((FW - IW) / 2 * SCALE), oy = Math.round((FH - IH) / 2 * SCALE), out = new Uint8Array(bd.bg);
  for (let y = 0; y < app.h; y++) for (let x = 0; x < app.w; x++) {
    const X = ox + x, Y = oy + y; if (X >= bd.w || Y >= bd.h) continue;
    const o = Y * bd.w + X, a = bd.alpha[o]; if (a <= 0) continue;
    const s = (y * app.w + x) * 3;
    for (let c = 0; c < 3; c++) out[o * 3 + c] = Math.min(255, Math.round(bd.bg[o * 3 + c] + a * app.rgb[s + c]));
  }
  return out;
}

async function record(cdp, base, lang) {
  const P = await openApp(cdp, base, { name: 'hero', lang, w: VW, h: VH, dsf: APP_DSF, boot: BOOT });
  await P.ev(`(() => { const b = document.querySelector('#mvw .mvb[data-mv="pipe"]'); if (!b) throw new Error('no tab pipe'); b.click(); return 1; })()`);
  await P.wait(`document.querySelectorAll('.plw .plcv .plnd').length >= 3 && !!document.querySelector('.plrtb')`, 'pipeline canvas');
  // Focus CSS: run overview + run bar + lit canvas + «By stage» table; editor side panels and palette hidden.
  await P.css('.plchips,.plapply,.plnames,.plpal,.plpan,.plcvt,.plw>.tkvs{display:none!important}'
    + '.plw .plgw{height:260px!important;min-height:0!important}'
    + '.plgw>.plcvw{height:260px!important;max-height:260px!important;min-height:0!important}'
    + '.plw .plcv{flex:1 1 0!important;min-height:0!important;height:auto!important}');
  const apply = i => P.ev(`(() => { window.__gifStep = ${JSON.stringify(STEPS[i])}; window.__gifMut(SESS);
    const f = document.getElementById('feed'); if (f) f._plw = ''; plPaint(); return 1; })()`);
  await apply(0);
  await sleep(1500);   // let the re-fit and fades settle before the first frame
  const shots = [];
  for (let i = 0; i < STEPS.length; i++) {
    if (i) await apply(i);
    const end = Date.now() + (i === STEPS.length - 1 ? 400 : STEP_MS);
    while (Date.now() < end) {
      const t = Date.now();
      shots.push({ t, png: (await P.S('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })).data });
      const left = FRAME_MS - (Date.now() - t); if (left > 0) await sleep(left);
    }
  }
  shots.push({ t: Date.now() + HOLD_MS, png: null });   // end marker: last frame holds HOLD_MS
  await P.close();
  return shots;
}

async function build(bd, shots, lang, framesDir) {
  const frames = [];
  for (let i = 0; i < shots.length - 1; i++) {
    const app = pngDecode(Buffer.from(shots[i].png, 'base64'));
    if (Math.abs(app.w - IW * SCALE) > 1) throw new Error('app capture ' + app.w + 'px, expected ' + IW * SCALE);
    frames.push({ rgb: composite(bd, app), ms: shots[i + 1].t - shots[i].t });
  }
  const hist = new Uint32Array(1 << 18);
  for (const f of frames) for (let o = 0; o < f.rgb.length; o += 3) hist[key6(f.rgb[o], f.rgb[o + 1], f.rgb[o + 2])]++;
  const pal = medianCut(hist, 255), map = mapper(pal);
  const gf = [];
  for (const f of frames) {
    const idx = new Uint8Array(bd.w * bd.h);
    for (let o = 0, p = 0; o < idx.length; o++, p += 3) idx[o] = map(key6(f.rgb[p], f.rgb[p + 1], f.rgb[p + 2]));
    const last = gf[gf.length - 1];
    if (last && Buffer.compare(Buffer.from(last.idx), Buffer.from(idx)) === 0) { last.ms += f.ms; continue; }   // merge identical frames
    gf.push({ idx, ms: f.ms });
  }
  gf.forEach(f => { f.cs = Math.max(2, Math.round(f.ms / 10)); });
  if (framesDir) {   // first, middle and last frame, as the GIF shows them (palette applied)
    fs.mkdirSync(framesDir, { recursive: true });
    [0, gf.length >> 1, gf.length - 1].forEach(k => {
      const rgb = new Uint8Array(bd.w * bd.h * 3);
      gf[k].idx.forEach((v, o) => { rgb[o * 3] = pal[v][0]; rgb[o * 3 + 1] = pal[v][1]; rgb[o * 3 + 2] = pal[v][2]; });
      fs.writeFileSync(path.join(framesDir, 'hero-' + lang + '-' + k + '.png'), pngEncode(bd.w, bd.h, rgb));
    });
  }
  while (pal.length < 255) pal.push([0, 0, 0]);
  pal.push([0, 0, 0]);   // index 255 = transparent
  return { buf: gifEncode(bd.w, bd.h, pal, gf), n: gf.length, cs: gf.reduce((a, f) => a + f.cs, 0) };
}

async function main() {
  const a = process.argv.slice(2), fi = a.indexOf('--frames'), framesDir = fi >= 0 ? path.resolve(a[fi + 1] || '') : '';
  const timer = setTimeout(() => { console.error('readme_gif: exceeded ' + DEADLINE_MS / 1000 + 's'); cleanup(); process.exit(1); }, DEADLINE_MS);
  const [base, wsUrl] = await Promise.all([startDemo(), startChrome()]);
  const cdp = new CDP(wsUrl); await cdp.open();
  fs.mkdirSync(OUT, { recursive: true });
  const bd = await backdrop(cdp, base);
  for (const lang of ['en', 'ko']) {
    const shots = await record(cdp, base, lang);
    const g = await build(bd, shots, lang, framesDir);
    const file = path.join(OUT, 'hero-' + lang + '.gif');
    fs.writeFileSync(file, g.buf);
    console.log(path.relative(ROOT, file) + '  ' + bd.w + 'x' + bd.h + '  ' + g.n + ' frames  ' + (g.cs / 100).toFixed(1) + 's  ' + Math.round(g.buf.length / 1024) + 'KB');
  }
  clearTimeout(timer);
  cdp.close();
  return 0;
}

main().then(code => { cleanup(); process.exit(code); }, e => { console.error('FAIL readme_gif: ' + (e && e.stack || e)); cleanup(); process.exit(1); });
