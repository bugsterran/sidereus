// Korean for core/feed/alarms/diff/work-log strings and the static header markup (index.html via hdrLang()).
Object.assign(I18N.ko, {
  // static markup (index.html) — painted by hdrLang()
  'The server was updated — this tab shows the old screen.': '서버가 새 버전으로 바뀌었어요 — 이 탭은 옛 화면입니다.',
  'Reload': '새로고침', 'Close this window (Esc)': '이 창 닫기 (Esc)',
  'AM': '오전', 'PM': '오후',   // CLK() ko clock marker
  '↑↓ move · Enter select · Esc close — conversation text is never searched (metadata only)': '↑↓ 이동 · Enter 선택 · Esc 닫기 — 대화 내용은 검색하지 않습니다(메타데이터만)',
  // feed
  '▴ Collapse': '▴ 접기', 'No messages match.': '해당하는 대화가 없습니다.',  // server health strip
  'Using previous values': '직전 값 사용 중', 'lookup is late, showing the previous value': '조회가 늦어 직전 값을 씁니다',
  // session state tooltips: in 06-i18n-b.js (one table only — a later Object.assign overrides an earlier one)
  // diff modal
  'No changes to show': '표시할 변경이 없습니다', 'new': '신규', 'deleted': '삭제',
  'newest first · click a row to see only that commit': '최신순 · 줄을 누르면 그 커밋만 봅니다', 'newest first': '최신순',
  'No commits pushed in this period': '이 기간에 푸시된 커밋이 없습니다',
  'No changes — everything is pushed': '변경 없음 — 푸시까지 끝난 상태입니다',
  'Collapse every directory': '모든 디렉터리를 접습니다', 'Expand every directory': '모든 디렉터리를 펼칩니다',
  '▸ Collapse all': '▸ 모두 접기', '▾ Expand all': '▾ 모두 펴기',
  '▴ Changes only': '▴ 변경 부분만', '▾ Show the whole file': '▾ 파일 전체 펼치기',
  'Switch between side-by-side (IntelliJ style) and unified diff': 'IntelliJ 처럼 좌우로 나란히 · 통합 diff 로 전환',
  'Side by side': '나란히', 'Unified': '통합', 'Previous change': '이전 변경', 'Next change': '다음 변경', '{n} changes': '변경 {n}곳', 'Commit history': '커밋 이력', '{n} unpushed · {m} pushed': '푸시 안 함 {n} · 푸시함 {m}', 'Loading the whole file…': '전체를 불러오는 중…',
  'Binary file — git gives no line diff': '바이너리 파일 — git 이 줄 단위 diff 를 주지 않습니다',
  'Drag to resize · double-click to reset': '끌어서 폭 조절 · 두 번 누르면 기본값',
  'Commits only': '커밋만',
  'Everything not on the remote yet — commits + uncommitted': '아직 원격에 없는 모든 것 — 커밋 + 미커밋',
  'Only what is committed but not pushed': '커밋했지만 아직 푸시하지 않은 것만',
  'Only what is not committed yet': '아직 커밋하지 않은 것만',
  'No upstream — only uncommitted changes can be shown': '업스트림 없음 — 미커밋만 볼 수 있습니다',
  'Viewing one commit — click a tab above to go back': '커밋 하나만 보는 중 — 위 칸을 누르면 돌아갑니다',
});
