// Korean for the History / Retrospect / Branches tabs, plus fixed server messages they pass through T().
//   ⚠Korean values must match the old Korean key (or the server's fixed `msg` text) byte for byte — the bridge maps them back.
Object.assign(I18N.ko, {
  // fixed server messages (sidereus/git.py, sidereus/commit_link.py) shown through T(msg)
  'This repository is not in the list': '이 저장소는 목록에 없습니다',
  'Only repositories touched by a session on screen can be viewed.': '화면의 세션이 만진 저장소만 볼 수 있습니다.',
  'A file path is required.': '파일 경로가 필요합니다.',
  'This file is not tracked by the repository.': '이 저장소가 추적하는 파일이 아닙니다.',
  'Not a commit hash.': '커밋 해시가 아닙니다.',
  'Not a git repository.': 'git 저장소가 아닙니다.',
});
