// Korean for the not-needed onlyOnJump stage (48b plPrLt · 48d node tooltip · 74c stepper tooltip) and stage rename (48d plRetitle · 48 plRenameWarn).
Object.assign(I18N.ko, {
  'not needed': '이번엔 불필요',
  'Not needed on this run — runs only on a loop-back': '이번 실행엔 필요 없음 — 되돌아왔을 때만 실행',
  'Rename the stage — loop-backs follow; saved with «Save»': '단계 이름 바꾸기 — 되돌아가기 연결도 따라 바뀝니다; «저장» 으로 기록',
  'Stage name is empty': '단계 이름이 비어 있습니다',
  'Stage name: at most 24 characters': '단계 이름: 24자 이하',
  'Stage name cannot contain / ] |': '단계 이름에 / ] | 는 쓸 수 없습니다',
  'A run of this pipeline is open — its running tags use the old stage name': '이 파이프라인의 실행이 열려 있습니다 — 진행 중인 태그는 옛 단계 이름을 씁니다',
  // Run summary chips at the timeline head (74c tlPlHeadHtml).
  'Stuck': '멈춤',
  'no activity {t}': '{t} 동안 기록 없음',
  'waiting for an answer': '답을 기다리는 중',
  '+{n} runs': '실행 {n}개 더',
  'Runs {n}': '실행 {n}', 'Pipeline runs': '파이프라인 실행', 'Pipeline runs — click to list them': '파이프라인 실행 — 눌러서 목록 보기',
  'Pipeline recording off': '파이프라인 기록 꺼짐',
  '«Apply» is off for this project, so its [pl:] tagged stages record no run — turn it on in Pipelines › Apply': '이 프로젝트는 «적용» 이 꺼져 있어 [pl:] 태그 단계가 실행으로 기록되지 않습니다 — 파이프라인 › 적용에서 켜세요',
  'Force delete': '강제 삭제',   // schema-breaking pipeline file (48 plBody)
  'Moves the file to the backup folder without reading it': '파일을 읽지 않고 백업 폴더로 옮깁니다',
  'Sidereus built-in': 'Sidereus 내장',   // borrowed pipeline labels (48h plBorrowLab)
  '{name} · from {proj}': '{name} · {proj}에서',
  'Defined in {proj} — read-only here': '{proj}에 정의됨 — 여기서는 보기 전용',
  'Unverified': '검증 없음',   // gate coverage (48d plGateCov)
  'No gate command — nothing machine-checks this stage': '게이트 명령 없음 — 이 단계는 기계가 채점하지 않습니다',
  'Gates {n}/{m}': '게이트 {n}/{m}', 'Stages machine-checked by a gate command: {n} of {m}': '게이트 명령이 기계로 채점하는 단계: {m}개 중 {n}개',
  '{n}/{m} done': '{n}/{m} 완료',
  // «Stage catalog» palette and «Guards» pane (48d plPalette · plGuardsPane)
  'Stage catalog': '단계 카탈로그', 'Click + or drag onto the canvas': '+ 를 누르거나 캔버스로 끌어다 놓으세요', '+ Add': '+ 추가',
  'Graded — brings a gate command': '채점됨 — 게이트 명령이 함께 들어갑니다', 'Not installed': '설치 안 됨', 'Tools installed': '도구 설치됨',
  'Needs the network': '네트워크 필요', 'Checks': '검사 내용', 'Gate idea': '게이트 예시',
  'Understand|catalog': '이해', 'Design|catalog': '설계', 'Build|catalog': '만들기', 'Quality|catalog': '품질', 'Security|catalog': '보안',
  'Consistency|catalog': '일관성', 'Review|catalog': '리뷰', 'Test|catalog': '테스트', 'Release|catalog': '릴리스', 'Guardrails|catalog': '안전장치', 'Research|catalog': '조사', 'Verify|catalog': '검증',
  'No match — + Custom stage creates "{name}"': '일치 없음 — + 직접 만들기로 "{name}" 단계를 만듭니다', 'in use': '사용 중', 'Already on the canvas — adding it again makes a numbered copy': '이미 캔버스에 있습니다 — 다시 추가하면 번호가 붙은 사본이 생깁니다',
  'Guards': '가드', 'The run stops when a required gate fails or loop-backs exceed the limit': '필수 게이트가 실패하거나 되돌림이 한도를 넘으면 실행을 멈춥니다',
  'No stage has a graded gate yet (check.sh --fast|--full, arch_checks.py --verify)': '아직 채점 게이트가 있는 단계가 없습니다 (check.sh --fast|--full, arch_checks.py --verify)',
  'Max loop-backs': '되돌림 한도',
});
