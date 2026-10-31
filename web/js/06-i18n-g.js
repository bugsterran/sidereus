// Korean for display text the server builds itself (names, failure signatures, errors, health warnings).
//   ★Failure signatures and burn row names are still Korean on the wire (stored cards read them as is); srvEn() below gives
//   their English at render time. ⚠Korean mode never reaches srvEn's English path.
Object.assign(I18N.ko, {
  // health strip — stale collector labels (sidereus/live.py _STALE_LABEL)
  'official sessions': '공식 세션', 'processes': '프로세스', 'watch processes': '감시 프로세스', 'tool runs': '툴 실행',
  // failure grade basis phrases (sidereus/failures.py _fail_grade)
  'api_error record (written by the harness itself)': 'api_error 기록(하네스가 직접 남긴 오류)',
  'Blocked by me — permission denial or hook block': '내가 막은 것 — 권한 거부·훅 차단',
  'A tool returned an error — part of the normal workflow': '도구가 오류를 돌려줌 — 작업 흐름의 일부',
  // quota denominator source (sidereus/usage.py)
  'calibrated': '보정', 'observed max': '관측 최대',
  // fixed error messages (sidereus/work.py, sidereus/structure.py, sidereus/demo.py, chat_server.py)
  'Only sessions shown on screen can be opened.': '화면에 있는 세션만 볼 수 있습니다.',
  'Could not find the session transcript.': '세션 트랜스크립트를 찾지 못했습니다.',
  "Could not find that subagent's record (it may not be written yet).": '그 서브에이전트의 기록을 찾지 못했습니다(아직 안 쓰였을 수 있습니다).',
  'Only projects shown on screen can be opened.': '화면에 있는 프로젝트만 볼 수 있습니다.',
  'This path cannot be read.': '읽을 수 없는 경로입니다.', 'Invalid range.': '잘못된 범위입니다.',
  'Could not read the file at that point in time.': '그 시점의 파일을 읽지 못했습니다.',
  'A room name and a target are required.': '방 이름과 대상이 필요합니다.',
  'The Structure tab is not used in demo mode': '데모 모드에서는 구조 탭을 쓰지 않습니다',
});
// Korean phrases the server still sends: failure signatures (sidereus/failures_scan.py, failures.py), burn row names
//   (sidereus/burn_scan.py, burn_usage.py), external blocked label (sidereus/ext.py). Callers holding such a field call srvEn().
//   ⚠Patterns are anchored to the exact server templates; a miss returns the source text (never breaks the screen).
const SRV_EN = {'도구 오류': 'Tool error', 'API 오류': 'API error', '백그라운드 작업': 'Background task',
                '승인 대기': 'Waiting for approval', '(이름 없음)': '(unnamed)', '기타': 'Other',
                '훅이 막음': 'Blocked by hook', '임시(스크래치패드)': 'Temporary (scratchpad)', '홈': 'Home'};
const SRV_EN_RX = [
  [/^기타 (\d+)개$/, 'Other ($1)'],
  [/^도구 오류 — /, 'Tool error — '],
  [/^훅이 막음 — /, 'Blocked by hook — '],
  [/^권한 거부 — 사용자가 거절$/, 'Permission denied — rejected by user'],
  [/^모델 일시 불가 — /, 'Model temporarily unavailable — '],
  [/^(?:서브)?에이전트 정지 — (\d+)초 무진전\(stream watchdog\)$/, 'Subagent stalled — no progress for $1s (stream watchdog)'],
  [/^절전 중 응답 끊김$/, 'Response cut off by sleep'],
  [/^연결 끊김\(mid-response\)$/, 'Connection closed (mid-response)'],
  [/^한도 도달 — /, 'Limit reached — '],
  [/^백그라운드 명령 exit (\d+)$/, 'Background command exit $1'],
  [/^감시 스크립트 exit (\d+)$/, 'Watch script exit $1'],
  [/^시간 초과$/, 'Timed out'],
  [/^(?:서브)?에이전트 (failed|killed)$/, 'Subagent $1'],
  [/^감시 (failed|killed)$/, 'Watch $1'],
  [/^백그라운드 (failed|killed)$/, 'Background $1'],
  [/^중단 — 내가 멈춤$/, 'Stopped — by me'],
  [/<경로>/g, '<path>'],
];
function srvEn(s){
  if(LANG !== 'en' || typeof s !== 'string' || !/[가-힣]/.test(s)) return s;
  if(Object.prototype.hasOwnProperty.call(SRV_EN, s)) return SRV_EN[s];
  let o = s;
  for(const [rx, en] of SRV_EN_RX) o = o.replace(rx, en);
  return o;
}
// Health strip warning (sidereus/warn.py `warn_once`): the server sends English `msg`/`msgEn` and `tv` parts for Korean.
function hlMsg(w){
  const m = String((w && w.msg) || '');
  if(LANG !== 'en') return w && Array.isArray(w.tv) ? w.tv.map(x => TV(x)).join(' · ') : m;   // tv = [{msg, vars}] parts
  return w && w.msgEn ? String(w.msgEn) : m;
}
