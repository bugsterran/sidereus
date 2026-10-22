// ★Language pack. UI text is written in English in the code; T('Save') shows it as-is in English and looks up
//   I18N.ko (English text -> Korean, split over 05a-i18n-en.js and 06-i18n-*.js) in Korean. A missing ko entry falls back
//   to the English source silently, so scripts/i18n_check.mjs is the guard.
//   ⚠Never swap keys for codes like `main.title` — the fallback only works while the key is the text itself.
//   Two Korean readings of one English text: T('Clear', 'tidy') looks up 'Clear|tidy' first (the context never shows).
//   ⚠No Korean -> English fallback: T() of Korean text returns it unchanged in English. Korean the server still sends
//   (failure signatures, burn row names) goes through srvEn() (06-i18n-g.js) at the caller.
const I18N = { ko: {
  // tabs
  'Chat': '채팅', 'Work log': '작업 내역', 'Timeline': '타임라인', 'Failures': '실패',
  'Tokens': '토큰', 'Structure': '구조', 'Branches': '브랜치', 'History': '이력', 'Settings': '설정',
  'Tool calls': '도구 호출', 'Errors': '오류', 'Files changed': '고친 파일', 'Last action': '마지막 동작',
  'Popup blocked — allow popups for this site.': '팝업이 차단됐습니다 — 이 사이트의 팝업을 허용해 주세요.',
  'Open in a new window': '새 창으로 열기',
  // work-log compose (36-wkcompose.js)
  'To': '받는 사람', "(subagent's parent session)": '(서브에이전트의 부모 세션)', 'No mailbox watch': '메일박스 감시 없음',
  'Not logged into the mailbox — cannot receive': '메일박스 미접속 — 받을 수 없습니다',
  'Waiting for permission — read on the next turn': '권한 대기 중 — 다음 턴에 읽힘',
  'Message this session — Enter to send · Shift+Enter for newline': '이 세션에 메시지 — Enter 전송 · Shift+Enter 줄바꿈',
  'This session cannot receive right now — it waits in the mailbox and is read when a watcher starts or a mailbox tool is called. Send anyway?': '이 세션은 지금 바로 받지 못합니다 — 메일박스에 쌓였다가 감시를 켜거나 메일박스 도구를 부를 때 읽힙니다. 보낼까요?',
  'Me': '나', 'Queued': '쌓임', 'Delivered': '전달됨', 'Reply': '답장',
  // ?ui=next preview (timeline control labels)
  'Replay': '재생', 'Refresh': '갱신', 'Range': '구간',
  'Background tone': '배경 톤', 'Black': '블랙', 'Grey': '그레이', 'Blue': '블루',
  'White': '화이트', 'System': '시스템',
  'Text size': '글자 크기', 'Scales text only; layout and widths stay the same.': '글자만 키우거나 줄입니다. 배치와 너비는 그대로입니다.',
  'System follows the OS: white when light, your last dark tone when dark.': '시스템은 OS 가 라이트면 화이트, 다크면 마지막 어두운 톤입니다.',
  // settings modal (header gear)
  '(unknown)': '(알 수 없음)',
  'Burndown curve': '번다운 곡선', 'Full history': '이력 전체',
  'Unread only': '읽지 않은 것만', 'Replay speed': '재생 속도', 'Refresh interval': '갱신 주기', 'Saved views': '저장된 뷰',
  'Show task description on subagent rows': '서브에이전트 행에 작업 설명 표시',
  'Labels subagent rows by the one-line task description given to the subagent, with the type as a chip. Off shows the type only.': '서브에이전트 행 이름을 서브에이전트에게 맡긴 한 줄 작업 설명으로 보이고, 유형은 옆 칩으로 둡니다. 끄면 유형만 보입니다.',
  // settings screen
  'Language': '언어', 'Korean': '한국어', 'Display language': '화면 언어',
  'Language used for the interface. Untranslated text stays in Korean.': '화면 문구에 쓰는 언어입니다. 번역이 없는 문구는 한국어 원문으로 보입니다.',
  'Display settings are saved on the viewer server and shared by every browser; saver mode applies to every session.': '화면 설정은 뷰어 서버에 저장돼 모든 브라우저가 같이 쓰고, 절약 모드는 모든 세션에 적용됩니다.',
  'Applies immediately, no reload needed.': '새로고침 없이 바로 바뀝니다.',
  // settings modal — saver switch (same files as /saver)
  'Saver mode': '절약 모드', 'Auto': '자동', 'Off': '끄기', 'On · stage 1': '켜기 수준 1', 'On · stage 2': '켜기 수준 2',
  'On · stage 3': '켜기 수준 3', 'On · stage 4': '켜기 수준 4', 'Target burn': '목표 소진율', 'Target time': '목표 시각',
  'Apply': '적용', 'Clear': '해제', 'off': '끔', 'default': '기본값', 'Manual on': '수동 켜기', 'Manual off': '수동 끄기',
  'stage {n}': '수준 {n}', 'not saving': '절약 모드 아님', 'In effect': '현재 적용', 'Save failed': '저장 실패',
  // settings modal — two-pane layout (category nav + row descriptions)
  'Display': '화면', 'Settings categories': '설정 분류', 'Mode': '작동 모드',
  'Color of the page background and panels.': '화면 바탕과 패널의 색입니다.',
  'Token widgets on the right': '오른쪽에 토큰 위젯 보기',
  'Keeps the weekly donut, daily, today-by-project and live charts under the session list. When off, they are in the Tokens tab and the 5h card at the top.': '주간 도넛·일별·당일 프로젝트별·실시간을 오른쪽 세션 목록 아래에 둡니다. 끄면 토큰 탭과 위 5시간 카드에서 봅니다.',
  'Live share since the last fetch (estimate)': '마지막 조회 이후 실시간분(추정)',
  'Show or collapse the usage burndown curve.': '사용량 번다운 곡선을 보이거나 접습니다.',
  'Show the full alert history or only unread cards.': '알림 목록에 이력 전체를 보일지, 읽지 않은 카드만 보일지 고릅니다.',
  // settings modal — alert policy («Alerts»)
  'Alerts': '알림', 'Alert level': '알림 수준', 'Important only': '중요만', 'Everything': '전부', 'Custom': '사용자 지정',
  'Badge': '배지', 'List only': '목록만', 'On': '켜기', 'Subagent done': '서브에이전트 완료', 'Subagent done|legacy': '에이전트 완료', 'Background done': '백그라운드 완료',
  'Important only badges questions, aborts and failures; completions collect quietly in the list.': '중요만은 질문 대기·중단·실패만 배지를 올리고, 완료 알림은 목록에만 조용히 쌓습니다.',
  'A session is waiting on a question or plan approval.': '세션이 질문이나 계획 승인을 기다립니다.',
  'A session was interrupted and needs a new instruction.': '세션이 중단되어 새 지시를 기다립니다.',
  'A subagent finished.': '서브에이전트 하나가 끝났습니다.',
  'A background job finished.': '백그라운드 작업 하나가 끝났습니다.',
  'Group repeats per session (30 min)': '같은 세션 반복 묶기 (30분)',
  'Consecutive cards with the same path and kind within 30 minutes collapse into one entry and count once on the badge.': '같은 경로·같은 종류의 카드가 30분 안에 이어지면 한 줄로 묶고 배지도 한 번만 셉니다.',
  '{n} subagents done': '서브에이전트 {n}개 완료', '{n} background jobs done': '백그라운드 {n}개 완료',
  'Show {n} more': '{n}개 더 보기', 'resumed {n}×': '이어서 {n}회',
  'click = mark read · groups as a whole · failures via the Read button': '클릭 = 읽음 · 묶음은 통째로 · 실패는 읽음 버튼',
  'Alerts — done · failed': '알림 — 완료·실패','{n} cards hidden by alert settings': '알림 설정에서 숨긴 카드 {n}개',
  // alerts panel (static header + list notes) · sidebar token card · quota legend
  'click = mark read': '클릭 = 읽음', 'Mark all read': '모두 읽음', 'Include older cards': '옛 카드까지 전부',
  'Done': '완료', 'Context nearly full': '컨텍스트 임박',
  'Clears the badge only — history is kept': '배지만 지웁니다 — 이력은 남습니다',
  'Collapse to unread cards only (history is not deleted)': '읽지 않은 카드만 남기고 접습니다(이력은 안 지웁니다)',
  'Showing the latest {n} — the other {m} are under `Full history`': '최근 {n}개만 보입니다 — 나머지 {m}개는 `이력 전체` 로',
  '{n} read cards hidden — turn off `Unread only` to see them': '읽은 카드 {n}개 숨김 — `읽지 않은 것만` 을 끄면 보입니다',
  'No unread cards — turn off `Unread only` to see {n} in history.': '읽지 않은 카드가 없습니다 — `읽지 않은 것만` 을 끄면 이력 {n}개가 보입니다.',
  'No alerts yet — they pile up here when a session ends its turn.': '아직 알림이 없습니다 — 세션이 턴을 끝내면 여기 쌓입니다.',
  'tail-capped': '꼬리제한', 'median': '중앙값',
  '⚠Very large transcripts are read only in their last 60MB — early hours may be missing.': '⚠아주 큰 기록 파일은 꼬리 60MB 만 읽습니다 — 이른 시간대가 빠질 수 있습니다.',
  'Auto picks the stage from the target burn; On pins a stage.': '자동은 목표 소진율로 수준을 정하고, 켜기는 수준을 고정합니다.',
  'Share of the 5-hour limit auto mode aims to use by the reset.': '자동 모드에서 5시간 리셋 때까지 쓸 한도 비율입니다.',
  'Paces usage to spread 100% of the limit until this time.': '이 시각까지 한도를 100% 나눠 쓰도록 맞춥니다.',
  'Timeline time played per second of replay.': '타임라인을 재생할 때 1초에 흐르는 시간입니다.',
  'How often the timeline reloads.': '타임라인을 다시 불러오는 간격입니다.',
  'Recent period the timeline shows.': '타임라인에 보여 줄 최근 기간입니다.',
  'Apply switches to that view and closes settings.': '적용을 누르면 그 뷰로 바뀌고 설정 창이 닫힙니다.',
  'integer 0-100': '0~100 정수', 'HH:MM format': 'HH:MM 형식',
  'Same file as /saver — applies to every CLI session from its next prompt.': '/saver 와 같은 파일입니다 — 모든 CLI 세션에 다음 프롬프트부터 적용됩니다.',
  // short labels
  'Agent': '에이전트', 'Model': '모델', 'Project': '프로젝트',
  'Repository': '저장소', 'None': '없음', 'All': '전체',
  'Close': '닫기', 'Cancel': '취소', 'Save': '저장', 'Reload|reread': '다시 읽기',
  'Loading…': '불러오는 중…', 'Loading…|read': '읽는 중…', 'Unknown': '알 수 없음',
  'Check the server': '서버를 확인하세요', 'Search': '검색', 'Send': '보내기',
} };
// Header count: a number glued to a unit, so the phrase-keyed T() dictionary cannot cover it.
// Timeline range label, shared by the timeline select and the settings modal.
function rangeLbl(h){
  if(h < 1) return LANG === 'en' ? Math.round(h*60) + ' min' : Math.round(h*60) + '분';
  return LANG === 'en' ? 'Last ' + h + 'h' : '최근 ' + h + '시간';
}
function cntText(n, shown){
  if(LANG === 'en') return n + ' msgs' + (shown ? ' (latest ' + shown + ')' : '');
  return n + '건' + (shown ? ' (최근 ' + shown + '개)' : '');
}
// ⚠Any number+unit goes through these — T() is phrase-keyed and cannot see a number glued to a unit.
//   U(n, <English unit>[, ctx]) → '5m' | n + UNIT_KO unit; '#…' units are a bare count in English ('#msgs' → '3' | 3 + ko count word).
const UNIT_KO = {'s':'초', 'm':'분', 'h':'시간', 'd':'일', 'mo':'개월', 'w':'주', '×':'회', ' lines':'줄', ' types':'종',
                 '#':'개', '#msgs':'건', '#people':'명', '#stages':'단계', ' files':'개', ' rooms':'개', ' max':'개까지',
                 'm left':'분 남음', 'm|ongoing':'분째'};
function U(n, u, c){
  if(typeof u !== 'string') return n + u;
  if(LANG === 'en') return n + (u.charAt(0) === '#' ? '' : u);
  const o = k => Object.prototype.hasOwnProperty.call(UNIT_KO, k), k = typeof c === 'string' && o(u + '|' + c) ? u + '|' + c : u;
  return n + (o(k) ? UNIT_KO[k] : u.charAt(0) === '#' ? '' : u);
}
// English count + noun with plural agreement: PL(1,'file') → '1 file', PL(3,'file') → '3 files'. en-only (Korean has no plural).
function PL(n, one, many){ return n + ' ' + (+n === 1 ? one : (many || one + 's')); }
// Relative phrasing around an already-formatted span: AGO(span) → ko span + ' ago' suffix | '5m ago'; LATER → ko 'later' suffix | 'in 5m'.
function AGO(t){ return LANG === 'en' ? t + ' ago' : t + ' 전'; }
function LATER(t){ return LANG === 'en' ? 'in ' + t : t + ' 뒤'; }
// Whole-sentence pair for text with numbers/HTML spliced in, where T() keys cannot fit: KE(<ko sentence>, `${n} hidden`).
//   ⚠Both arguments are evaluated; the ko argument must stay the exact original expression so Korean output is byte-identical.
function KE(ko, en){ return LANG === 'en' ? en : ko; }
// Feed "load older" bar — shared by the first paint and the in-place update.
function olderTxt(hidden){
  const k = Math.min(SHOW_STEP, hidden);
  return LANG === 'en' ? '▲ Load ' + k + ' older<span>· ' + hidden + ' hidden</span>'
                       : '▲ 이전 '+k+'개 더 보기<span>· 숨김 '+hidden+'건</span>';
}
// Two-part span (ko hours + minutes) | '3h 5m' (minutes in). Shared by the several duration formatters below.
function HM(m){
  return m>=1440 ? U(Math.floor(m/1440),'d')+' '+U(Math.floor((m%1440)/60),'h')
       : (m>=60 ? U(Math.floor(m/60),'h')+' '+U(m%60,'m') : U(m,'m'));
}
// Clock (ko PM-marker + '08:49') | '8:49 PM' and date+clock (9/27 + ko clock) | '9/27 2:59 AM'.
// ⚠The ko clock is built from the I18N dictionary, not Intl ko-KR: a runtime without Korean locale data
//   (small ICU, some CI node builds) printed 'PM 01:05' in the Korean UI. Same shape as ko-KR 2-digit (12 for 0h).
// ⚠toLocaleTimeString(loc, opts) builds a new Intl formatter per call (top self-time in a poll profile), so the en
//   formatter is cached on CLK itself; invalid dates keep the old path (format() would throw).
function CLK(d){
  if(isNaN(d.getTime())) return d.toLocaleTimeString();
  if(LANG !== 'en'){
    const h = d.getHours(), z = n => String(n).padStart(2, '0');
    return T(h < 12 ? 'AM' : 'PM') + ' ' + z(h % 12 || 12) + ':' + z(d.getMinutes());
  }
  const c = CLK.fmt || (CLK.fmt = {});
  return (c.en || (c.en = new Intl.DateTimeFormat('en-US',{hour:'numeric',minute:'2-digit'}))).format(d);
}
function MDCLK(d){ return (d.getMonth()+1)+'/'+d.getDate()+' '+CLK(d); }
// 7d reset in one format for card, popover, status bar and drawer: abs '10/5 7:00 PM' · rel 'in 9h'
//   (whole days/hours — four places used to print four different shapes). Narrow spots drop a part, never reword it.
function REL7(m){ return LATER(m >= 1440 ? U(Math.floor(m / 1440), 'd') : m >= 60 ? U(Math.floor(m / 60), 'h') : U(m, 'm')); }
function RST7(d, nowMs){
  return { abs: MDCLK(d), rel: REL7(Math.max(0, Math.round((d - (nowMs || Date.now())) / 60000))) };
}
// Zero-padded 24h 'HH:MM' from epoch seconds or a Date (language-neutral, unlike CLK).
//   o.sec → ':SS' · o.date true → 'MM/DD ' prefix, 'other' → only when not today · o.dsep = date separator ('/').
function hhmm(ts, o){
  o = o || {};
  const d = ts instanceof Date ? ts : new Date(ts * 1000), z = n => String(n).padStart(2, '0');
  const day = o.date && (o.date !== 'other' || d.toDateString() !== new Date().toDateString())
    ? z(d.getMonth() + 1) + (o.dsep || '/') + z(d.getDate()) + ' ' : '';
  return day + z(d.getHours()) + ':' + z(d.getMinutes()) + (o.sec ? ':' + z(d.getSeconds()) : '');
}
function LOC(){ return LANG === 'en' ? 'en-US' : 'ko-KR'; }   // date/time locale follows the UI language
// Nothing saved -> follow the browser (en* -> en, else ko) so a first run is readable without finding Settings.
const langPick = (saved, nav) => (saved === 'en' || saved === 'ko') ? saved : (/^en\b/i.test(nav || '') ? 'en' : 'ko');
let LANG =(() => { let s; try { s = UIS.mbLang; } catch(e){ s = null; }   // blocked storage = nothing saved
                    try { return langPick(s, navigator.language); } catch(e){ return 'ko'; } })();
// ⚠Own keys only everywhere below: a bare d[s] returns Object.prototype members for 'constructor', 'toString', ...
function T(s, c){
  const own = (d, k) => Object.prototype.hasOwnProperty.call(d, k);
  if(LANG === 'en') return s;   // English is the source text
  const d = I18N.ko;
  if(typeof c === 'string' && own(d, s + '|' + c)) return d[s + '|' + c];
  return own(d, s) ? d[s] : s;
}
// Server reply {msg: fixed key with {k} slots, vars: {k: value}} -> translated text; values never go through T().
function TV(j){
  if(!j || !j.msg) return '';
  const v = (j.vars && typeof j.vars === 'object') ? j.vars : {};
  return T(j.msg).replace(/\{(\w+)\}/g, (all, k) => Object.prototype.hasOwnProperty.call(v, k) ? String(v[k]) : all);
}
// ⚠User data (project/agent names) must not go through T() or srvEn(): a name equal to a dictionary key or server phrase
//   would be translated. Only the server's fixed placeholders are translated here (sidereus/burn_scan.py, sidereus/failures.py).
function TN(s){
  // sidereus/burn.py subagent row '<name> (subagent, in Korean)': only the suffix is translated, the name stays user data.
  if(LANG === 'en' && typeof s === 'string' && / \(서브에이전트\)$/.test(s)) return TN(s.slice(0, -9)) + ' (subagent)';
  // ⚠«Agent» = label on cards saved before the 2026-09-25 rename; singular here (T() of «Subagents» is the plural header).
  if(s === '서브에이전트' || s === '에이전트') return LANG === 'en' ? 'Subagent' : '서브에이전트';
  // sidereus/burn_scan.py _slug_name placeholders stay Korean on the wire (stored group key); translated only here.
  return (s === '백그라운드 작업' || s === '임시(스크래치패드)' || s === '홈' || /^기타 \d+개$/.test(s)) ? srvEn(s) : s;
}
// Pipelines-first: nothing saved / invalid / old 'work' (now a modal) lands on Pipelines; Timeline only if pipe was feature-off.
// ⚠mbTabsOff = tabs whose feature was off at the last poll (92 buildMv); without it a remembered tab calls its 404 route.
let mainView = (() => { try { const off = JSON.parse(UIS.mbTabsOff || '[]'), ok = v => !(Array.isArray(off) && off.includes(v)) && (v === 'chat' || v === 'time'
                                      || v === 'token' || v === 'struct'
                                      || v === 'br' || v === 'hist' || v === 'retro' || v === 'pipe');
                              // «Preferences» mbStartView: a tab key wins; 'last'/unset reopens mbMainView.
                              // Per tab: a refresh keeps this tab's own view (08 tabOwn); mbStartView only picks a new tab's first view.
                              // URL hash (/#structure) wins over both; popups never read it (92 mvHashKey).
                              // ⚠typeof guards: tests run this file alone, without 00-core/92.
                              const h = (typeof mvHashKey !== 'function' || typeof ISPOP === 'undefined' || ISPOP || ISWP || ISBP) ? null : mvHashKey(location.hash);
                              const o = tabOwn('mbMainView'), s = UIS.mbStartView, v = ok(h) ? h : ok(o) ? o : ok(s) ? s : UIS.mbMainView;
                              // ⚠'fail' (tab removed 2026-09-23, now alerts) is not listed -> default tab.
                              return ok(v) ? v : ok('pipe') ? 'pipe' : 'time'; }
                        catch(e){ return 'pipe'; } })();
if(document.documentElement) document.documentElement.dataset.mv = mainView;   // same hook setMainView keeps current (75-structure.css)
let place='all';                // 'all' | 'dm' | 'room:<name>'
let filter='all', q='';
const feed=document.getElementById('feed'), jump=document.getElementById('jump');

