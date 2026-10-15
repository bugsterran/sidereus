// «Security n/m» row at the top of the «Evaluation» panel (48i): repo security checks from GET /api/pipelines/eval — ids and verdicts only.
const PLE_SEC = { 'security-policy': ['Security policy', 'Add SECURITY.md (root, .github/ or docs/)'],
  'license': ['License', 'Add a LICENSE file'],
  'pinned-deps': ['Pinned dependencies', 'Commit a lockfile next to each manifest'],
  'dep-update-tool': ['Dependency updates', 'Add Dependabot or Renovate config'],
  'secret-gate': ['Secret scan', 'Add a gitleaks gate (checks-security)'],
  'sast-gate': ['Static analysis', 'Add a semgrep or bandit gate'],
  'dep-audit-gate': ['Dependency audit', 'Add an npm audit or osv-scanner gate'],
  'binary-artifacts': ['Binary artifacts', 'Remove tracked binaries'] };
let PLE_SEC_OPEN = false;   // ⚠the panel is rebuilt on every repaint: the <details> open state lives here
// Pure: nothing when absent; failing checks only (pass and na omitted); an unknown id shows as-is with no hint.
function plEvalSec(sec, open){
  if(!sec || typeof sec !== 'object') return '';
  const fails = (Array.isArray(sec.checks) ? sec.checks : []).filter(c => c && c.v === 'fail' && c.id);
  const n = sec.n | 0, m = sec.m | 0, cls = 'plesec' + (n < m ? ' plesec-lo' : '');
  const head = esc(TV({msg: 'Security {n}/{m}', vars: {n: n, m: m}}));
  if(!fails.length) return '<div class="' + cls + '"><span class=plesech>' + head + '</span></div>';
  return '<details class="' + cls + '" data-plesec' + (open ? ' open' : '') + '><summary class=plesech>' + head + '</summary><ul>'
    + fails.map(c => { const d = PLE_SEC[c.id];
      return '<li><b>' + esc(d ? T(d[0]) : String(c.id)) + '</b>' + (d ? ' <span>' + esc(T(d[1])) + '</span>' : '') + '</li>'; }).join('') + '</ul></details>';
}
document.addEventListener('toggle', e => {
  const t = e.target;
  if(!t || !t.matches || !t.matches('[data-plesec]')) return;
  PLE_SEC_OPEN = t.open;
  if(typeof plEvalPlace === 'function') plEvalPlace();   // the popover grew: re-anchor (flipY)
}, true);
