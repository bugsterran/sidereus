// Korean for the token tab, sidebar token widgets, quota/burndown/credit and saver badge (45-tokens.js · 55-saver-quota.js).
Object.assign(I18N.ko, {
  // 45-tokens.js
  '\nNo records on this day': '\n이 날은 기록이 없습니다',
  'Weekly token share': '주간 토큰 비중',
  // 55-saver-quota.js — saver badge
  'Judged by **how many minutes off the target time you land at this rate**.\nOn pace within ±10 min · fast/slow up to 30 min · beyond that, way too fast/slow\nThe verdict changes only once a bound is passed by 3 min, so it does not flicker at the edge.\nThe hook (saver.py) makes the call and adjusts on its own.': '이대로 가면 **목표 시각과 몇 분 어긋나나**로 판정합니다.\n적정 ±10분 이내 · 빠름·느림 30분까지 · 그보다 크면 많이 빠름·많이 느림\n경계에서 깜빡이지 않게 경계를 3분 넘어야 판정이 바뀝니다.\n판정과 조절은 훅(saver.py)이 알아서 합니다.',
  // credit badge · burndown · local quota fallback
  '\nWhen the limit resets (5h row above), usage is back to the included allowance.': '\n한도가 리셋되면(위 5h 줄) 다시 무료 구간으로 돌아갑니다.',
  'Counting usage…': '사용량 집계 중…',
  'ccusage is counting past usage (cold start 40-100s). 5h and weekly appear when it finishes.': 'ccusage 로 과거분을 세는 중입니다(콜드 40~100초). 끝나면 5시간·주간이 나옵니다.',
  'No quota %': '할당량 % 없음',
  'Put the weekly reset time from /usage in usage-anchor.json to show it here': '/usage 의 주간 리셋 시각을 usage-anchor.json 에 넣으면 여기에 표시됩니다',
  'Reset not set': '리셋 미설정',
});
