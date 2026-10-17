// Korean for the timeline and structure tabs (70-82). English text is the key, as in 05-i18n.js.
Object.assign(I18N.ko, {
  'Replay — the cursor walks from the left edge of the window to the right by itself.\nThe right side (time not reached yet) is masked, so the day appears to fill in.\nClick a bar cell midway to continue from there.': '리플레이 — 커서가 창 왼쪽부터 오른쪽으로 스스로 걸어갑니다.\n오른쪽(아직 안 온 시간)은 가려서 하루가 채워지는 것처럼 보입니다.\n도중에 막대 칸을 누르면 그 자리부터 이어 갑니다.',
  'Could not fetch — showing the last data received': '가져오지 못했습니다 — 아래는 마지막으로 받은 것입니다',
});
// Timeline toolbar «Changes» chip (77-timeline-git.js tlgChipInner).
Object.assign(I18N.ko, {
  'Changes|chip': '변경', 'Auto (latest active)|chip': '자동(최근 활동)', '{n} shared': '공유 {n}개',
  'Also edited by another live session within 30 min:': '다른 실행 중 세션도 30분 안에 고친 파일:',
  'Open the changes in the diff window (git · view only)': '변경 내용을 diff 창에서 열기 (git · 보기만)',
  'Find a session': '세션 찾기', 'auto|mark': '자동',
});
// Diff window baselines + untracked toggle (35c-worklog-pop.js diffShow).
Object.assign(I18N.ko, {
  'Include untracked files': '추적 안 된 파일 포함',
  'Since session start|diff': '세션 시작 이후', 'vs main / master|diff': 'main(master) 대비',
  'Every change since this session started — commits + uncommitted': '이 세션이 시작된 뒤의 모든 변경 — 커밋 + 미커밋',
  'Everything since this branch left main / master — commits + uncommitted': '이 브랜치가 main(master)에서 갈라진 뒤의 모든 변경 — 커밋 + 미커밋',
  'Session unknown — open this window from the Timeline «Changes» chip': '세션을 알 수 없습니다 — 타임라인 «변경» 칩에서 이 창을 여세요',
  'Since {n} — pick a scope above to go back': '{n} 이후 — 위에서 범위를 고르면 돌아갑니다',
});
