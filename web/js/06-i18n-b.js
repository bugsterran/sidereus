// Korean for the session list, drawer, chat chrome, saved views and settings (40·90·92·95·97·99). English text is the key.
Object.assign(I18N.ko, {
  'No matching sessions.': '맞는 세션이 없습니다.',
  'Views': '보기',
  'That session is not in the list — it probably dropped out between polls': '그 세션의 행이 목록에 없습니다 — 사이 폴에서 빠진 것 같습니다',
  'idle filter': '유휴 필터', 'git filter': 'git 필터', 'state filter': '상태 필터',
  "View this session's changes (diff)": '이 세션의 변경(diff) 보기',
  "Click to view this session's changes (diff)": '눌러서 이 세션의 변경(diff) 보기',
  'Claude': '클로드',
  '— Doing now': '— 지금 하는 일',
  'Spawned by the subagent above': '위 서브에이전트가 띄운 것',
  // session state tooltips (TIP / BLKTIP / WAITTIP in 20-session-state.js)
  'Running a tool — the tool name beside it is what runs now (long commands keep the screen quiet)': '도구가 도는 중 — 옆의 도구 이름이 지금 실행 중인 것입니다(오래 걸리는 명령이면 화면이 조용합니다)',
  'The model is processing a tool result — the next tool call or reply comes soon': '도구 결과를 받아 모델이 처리하는 중 — 곧 다음 도구나 응답이 나옵니다',
  '★Needs you to continue — awaiting an answer or plan approval': '★네 답이 있어야 진행됩니다 — 질문·계획 승인 대기',
  'Finished its reply and awaits your input — it stays put until you give another instruction (your turn)': '할 말을 끝내고 당신의 입력을 기다립니다 — 추가 지시가 없으면 그대로 멈춰 있습니다(사람 차례)',
  'Interrupted by you (Esc) — it moves again only with a new instruction': '사용자가 중단(esc)한 자리 — 다시 지시해야 움직입니다',
  'No claude process — an ended session (use --resume to continue)': 'claude 프로세스가 없습니다 — 끝난 세션(이어서 하려면 --resume)',
  'The CLI process went away without an end event (killed, terminal closed) — it leaves the list in 10 min. «Disconnected?» is a guess: no pid and no news for over 20 min': 'CLI 프로세스가 종료 알림 없이 사라졌습니다(강제 종료·터미널 닫힘) — 10분 뒤 목록에서 빠집니다. «끊김?» 은 pid 없이 20분 넘게 소식이 없다는 추정입니다',
  'Could not read the process state — not assumed either way': '프로세스 상태를 읽지 못했습니다 — 단정하지 않습니다',
  '★Needs you to approve or choose — a tool call is pending with no sign of running (a fast tool taking long, or Bash with no process). MCP tools can legitimately take long, so they are not judged': '★네가 승인·선택을 눌러야 움직인다 — 도구 호출이 떠 있는데 실행 흔적이 없다(빠른 도구가 오래 걸려 있거나, Bash 인데 실행 프로세스가 없음). MCP 도구는 오래 걸리는 게 정상일 수 있어 판정하지 않는다',
  'The model turn ended but background work is still running — the session moves again when results arrive (not your turn yet)': '모델 턴은 끝났지만 백그라운드가 아직 돌고 있다 —결과가 오면 이 세션이 다시 움직인다(사람이 손 댈 차례가 아니다)',
  // chat chrome (rooms · saved views · poll)
  'no messages yet': '아직 글이 없습니다',  'Could not mark as read — check the server': '읽음 처리를 못 보냈습니다 — 서버를 확인하세요',
  '(unnamed)': '(이름 없음)', 'This view is in an old format and could not be restored': '이 뷰는 옛 형식이라 복원하지 못했습니다',
  'Go back to this combination': '이 조합으로 돌아갑니다', 'Delete this view': '이 뷰를 지웁니다',
  'Name for the current filter combination?': '지금의 필터 조합을 무슨 이름으로 저장할까요?',
  'A view with this name exists — overwrite it?': '같은 이름의 뷰가 있습니다 — 덮어쓸까요?',
});
