// ── File-type icons, IDE-style: one table + one SVG builder shared by every file list (timeline rail, branch work unit) ──
// Extensions show as IDE-style glyphs rather than text chips (faster to scan).
// ⚠All glyphs are drawn here from basic shapes (no brand logos, icon fonts or theme assets; THIRD_PARTY_NOTICES.md).
// Colours: css/07-file-icons.css (.ftic-<key> sets the hue; lightness/chroma per theme). Adding a type = FI_EXT entry (+ glyph/hue if new).
const FI_EXT = {
  js:'js', mjs:'js', cjs:'js', ts:'ts', mts:'ts', cts:'ts', jsx:'jsx', tsx:'tsx',
  py:'py', pyi:'py', pyw:'py', html:'html', htm:'html', xml:'html', vue:'html', svelte:'html',
  css:'css', scss:'css', sass:'css', less:'css', json:'json', jsonl:'json', jsonc:'json', json5:'json',
  md:'md', markdown:'md', mdx:'md', txt:'txt', log:'txt', rst:'txt', csv:'txt', tsv:'txt',
  yml:'config', yaml:'config', toml:'config', ini:'config', cfg:'config', conf:'config', properties:'config', env:'config',
  sh:'sh', bash:'sh', zsh:'sh', fish:'sh', sql:'sql', java:'java', kt:'kt', kts:'kt', go:'go', rs:'rs',
  png:'image', jpg:'image', jpeg:'image', gif:'image', webp:'image', svg:'image', ico:'image', bmp:'image', avif:'image',
  lock:'lock', mk:'make', dockerfile:'docker',
};
// Whole-name matches win over the extension (lower-cased).
const FI_NAME = {
  dockerfile:'docker', '.dockerignore':'docker', 'docker-compose.yml':'docker', 'docker-compose.yaml':'docker', 'compose.yaml':'docker',
  makefile:'make', gnumakefile:'make', '.gitignore':'git', '.gitattributes':'git', '.gitmodules':'git', '.gitkeep':'git',
  'package-lock.json':'lock', 'pnpm-lock.yaml':'lock', 'npm-shrinkwrap.json':'lock', '.env':'config',
};
// name or path -> icon key; 'file' when nothing matches.
function fileIcoKey(name){
  const n = String(name || '').split('/').pop().toLowerCase();
  if(FI_NAME[n]) return FI_NAME[n];
  if(/^readme(\.|$)/.test(n)) return 'readme';
  if(/^\.env\./.test(n)) return 'config';
  const i = n.lastIndexOf('.');
  return (i > 0 && FI_EXT[n.slice(i + 1)]) || 'file';
}
// 16x16 glyphs. currentColor = the type hue; .fo = ink on a filled tile; .f2 = second tone.
const FI_S = ' fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"';
const FI_TILE = '<rect x="1.5" y="1.5" width="13" height="13" rx="3" fill="currentColor"/>';
const FI_TX = (t, x) => '<text x="' + (x || 8) + '" y="11.6" text-anchor="middle" class="fo">' + t + '</text>';
const FI_PAGE = '<path d="M3.5 1.5h5.8l3.2 3.2v9.8h-9z M9.3 1.5v3.2h3.2"' + FI_S + ' stroke-width="1.2"/>';
const FI_ATOM = '<ellipse cx="8" cy="8" rx="6.4" ry="2.7" transform="rotate(-35 8 8)"' + FI_S + ' stroke-width="1.3"/>'
  + '<circle cx="8" cy="8" r="1.9" fill="currentColor"/><circle cx="13.2" cy="4.4" r="1.4" class="f2"/>';
const FI_SVG = {
  js: FI_TILE + FI_TX('JS'), ts: FI_TILE + FI_TX('TS'), jsx: FI_ATOM, tsx: FI_ATOM,
  py: '<path d="M4.5 1.5h7a3 3 0 0 1 3 3V8h-13V4.5a3 3 0 0 1 3-3z" fill="currentColor"/>'
    + '<path d="M1.5 8h13v3.5a3 3 0 0 1-3 3h-7a3 3 0 0 1-3-3z" class="f2"/>' + FI_TX('py'),
  java: FI_TILE + '<path d="M4.5 4.2h7" stroke-width="1.3" class="fs"/>' + FI_TX('J'),
  kt: FI_TILE + '<path d="M14.5 6.8v4.7a3 3 0 0 1-3 3H6.8z" class="f2"/>' + FI_TX('K', 7),
  go: '<rect x="1" y="3" width="14" height="10" rx="5" fill="currentColor"/>' + FI_TX('GO'),
  rs: '<path d="M8 1.2 14.2 4.6v6.8L8 14.8 1.8 11.4V4.6z" fill="currentColor"/>' + FI_TX('R'),
  html: '<path d="M5.2 4.2 1.8 8l3.4 3.8M10.8 4.2 14.2 8l-3.4 3.8M9.1 3 6.9 13"' + FI_S + ' stroke-width="1.6"/>',
  css: '<path d="M6.3 2.5 5.1 13.5M10.9 2.5 9.7 13.5M2.8 6h11M2.2 10h11"' + FI_S + ' stroke-width="1.6"/>',
  json: '<path d="M6 2.5c-1.6 0-2 .7-2 2v1.6c0 1-.5 1.6-1.6 1.9 1.1.3 1.6.9 1.6 1.9v1.6c0 1.3.4 2 2 2'
    + 'M10 2.5c1.6 0 2 .7 2 2v1.6c0 1 .5 1.6 1.6 1.9-1.1.3-1.6.9-1.6 1.9v1.6c0 1.3-.4 2-2 2"' + FI_S + ' stroke-width="1.5"/>',
  md: '<rect x="1" y="3.5" width="14" height="9" rx="1.8"' + FI_S + ' stroke-width="1.2"/>'
    + '<path d="M3.6 10.2V5.8l1.8 2.2 1.8-2.2v4.4M11 5.8v4.2M9.3 8.4l1.7 1.8 1.7-1.8"' + FI_S + ' stroke-width="1.3"/>',
  txt: FI_PAGE + '<path d="M5.5 8h5M5.5 10.5h5M5.5 13h3"' + FI_S + ' stroke-width="1.1"/>',
  readme: '<path d="M8 4.2C6.5 3 4.3 2.7 1.8 3v9.3c2.5-.3 4.7 0 6.2 1.2 1.5-1.2 3.7-1.5 6.2-1.2V3C11.7 2.7 9.5 3 8 4.2zM8 4.2v9.3"'
    + FI_S + ' stroke-width="1.3"/>',
  config: '<circle cx="8" cy="8" r="5" fill="none" stroke="currentColor" stroke-width="2.6" stroke-dasharray="1.9 2.02"/>'
    + '<circle cx="8" cy="8" r="3.6" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="8" cy="8" r="1" fill="currentColor"/>',
  sh: '<rect x="1.5" y="2.5" width="13" height="11" rx="2"' + FI_S + ' stroke-width="1.2"/>'
    + '<path d="M4.3 6.2 6.6 8.2 4.3 10.2M8.2 10.6h3.6"' + FI_S + ' stroke-width="1.5"/>',
  sql: '<ellipse cx="8" cy="4" rx="5.5" ry="2"' + FI_S + ' stroke-width="1.3"/>'
    + '<path d="M2.5 4v8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2V4M2.5 8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2"' + FI_S + ' stroke-width="1.3"/>',
  image: '<rect x="1.5" y="2.5" width="13" height="11" rx="2"' + FI_S + ' stroke-width="1.2"/><circle cx="5.4" cy="6.2" r="1.3" fill="currentColor"/>'
    + '<path d="M2.2 12.4 6.2 8.7l2.6 2.4 2-1.8 3.2 3"' + FI_S + ' stroke-width="1.3"/>',
  lock: '<path d="M5.2 7V5.2a2.8 2.8 0 0 1 5.6 0V7"' + FI_S + ' stroke-width="1.5"/>'
    + '<rect x="3" y="7" width="10" height="7.5" rx="1.6" fill="currentColor"/><circle cx="8" cy="10.7" r="1.2" class="fo"/>',
  git: '<circle cx="4.5" cy="3.6" r="1.7"' + FI_S + ' stroke-width="1.3"/><circle cx="4.5" cy="12.4" r="1.7"' + FI_S + ' stroke-width="1.3"/>'
    + '<circle cx="11.5" cy="6" r="1.7"' + FI_S + ' stroke-width="1.3"/><path d="M4.5 5.3v5.4M11.5 7.7c0 2.2-2.1 2.8-5.4 3.7"' + FI_S + ' stroke-width="1.3"/>',
  docker: '<path d="M8 1.8 14 5v6.2L8 14.4 2 11.2V5zM2 5l6 3.2L14 5M8 8.2v6.2"' + FI_S + ' stroke-width="1.3"/>',
  make: '<path d="M2.8 13.2 10 6"' + FI_S + ' stroke-width="2"/><path d="M8.9 2.7l4.4 4.4-1.8 1.8-4.4-4.4z" fill="currentColor"/>',
  file: FI_PAGE,
};
// <i class="ftic ftic-KEY"> (⚠not .fic — 30-diff.js/50-layout-feed.css own that) with the inline SVG; fixed box so names beside it truncate, not the icon.
function fileIco(name, px){
  const k = fileIcoKey(name), s = px || 14;
  return '<i class="ftic ftic-' + k + '" aria-hidden=true><svg viewBox="0 0 16 16" width=' + s + ' height=' + s + '>' + FI_SVG[k] + '</svg></i>';
}
