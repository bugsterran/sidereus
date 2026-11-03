// Pipeline stage display names per language, keyed by the saved Korean title (48c plgShow). Display only: saved titles, [pl:] tags and matching stay Korean.
// The «Stage catalog» palette follows the UI language — Korean mode shows the Korean title as-is; a new language = a new table here.
const PLG_NAMES = { en: {
  '설계': 'Design', '구현': 'Implement', '검증': 'Verify', '리뷰': 'Review', '재검증': 'Re-verify', '최종 검증': 'Re-verify', '재현': 'Reproduce',
  '원인': 'Root cause', '수정': 'Fix', '회귀': 'Regression', '트리아지': 'Triage', '라이브 검증': 'Live verify', '탐색': 'Explore',
  'AI 설정 점검': 'AI config review', '프롬프트 검증': 'Prompt check',
  // «Stage catalog» titles (sidereus/stage_catalog.json title.en) and former palette titles still found in saved pipelines
  '코드 지도': 'Code map', '린트·정적 분석': 'Lint + static analysis', '단위 테스트': 'Unit tests', '비밀 스캔': 'Secret scan',
  '의존성 감사': 'Dependency audit', 'API 계약 비교': 'API contract diff', '레거시 동등성': 'Legacy parity',
  '요구 정리': 'Requirements', '코드 탐색': 'Code explore', '테스트 작성': 'Write tests', '마이그레이션': 'Migration', '문서화': 'Docs',
  '테스트 실행': 'Run tests', '보안 점검': 'Security check', '성능 측정': 'Perf measure', 'UX 리뷰': 'UX review', '릴리스 노트': 'Release notes',
  '커밋 정리': 'Commit tidy', '배포 체크': 'Deploy checklist',
  'API 설계': 'API design', '데이터·마이그레이션 계획': 'Data + migration plan', '위협 모델': 'Threat model', '다국어 문자열': 'i18n strings',
  '통합 테스트': 'Integration tests', 'E2E 테스트': 'E2E browser test', '접근성 점검': 'Accessibility check', '변이 테스트': 'Mutation testing',
  '타입 검사': 'Type check', '복잡도·중복 점검': 'Complexity + duplication', '커버리지 기준': 'Coverage threshold', '정적 보안 분석': 'SAST',
  '라이선스 점검': 'License check', '컨테이너·IaC 스캔': 'Container + IaC scan', '스키마 정합성': 'Schema drift', '문서 리뷰': 'Docs review',
  '교차 리뷰': 'Second-opinion review', '변경 기록': 'Changelog', '빌드 산출물': 'Build artifact', '배포 후 스모크': 'Post-deploy smoke test',
  '롤백 계획': 'Rollback plan', '사람 승인': 'Human approval', '메일박스 알림': 'Mailbox notify',
  '웹 조사': 'Web research', '선행 연구': 'Prior art + papers', '라이브러리 문서 확인': 'Library + docs lookup', '선택지 비교': 'Option comparison',
  '스파이크': 'Spike + prototype', '유사 도구 조사': 'Reference survey', '개선': 'Improve', '성능 개선': 'Optimize', '코드 정리': 'Cleanup',
  '읽기 계획': 'Reading plan', '모듈 그리기': 'Draw modules', '흐름 그리기': 'Draw flows', '점검 계획': 'Check plan', '점검': 'Check', '업데이트': 'Update',
  '검사 실행': 'Run checks', '보안 검사': 'Security checks', '화면 확인': 'Screen check', '수용 확인': 'Acceptance check',
  // «Standard templates» stages (sidereus/pipeline_std.py STD)
  '실패 테스트': 'Failing test', '기준선': 'Baseline', '계획': 'Plan', '리팩토링': 'Refactor', '측정': 'Measure', '병목 분석': 'Bottleneck analysis',
  '최적화': 'Optimise', '동등성 검증': 'Equivalence check', '재측정': 'Re-measure', '영향 평가': 'Impact assessment', '패치': 'Patch',
  '보안·회귀 테스트': 'Security · regression tests', '보안 리뷰': 'Security review', '배포 확인': 'Deploy check', '조사': 'Investigate',
  '버전 올림': 'Bump versions', '깨진 곳 수정': 'Fix breakage', '전체 테스트': 'Full test', '분류': 'Classify', '완화': 'Mitigate',
  '복구 확인': 'Confirm recovery', '근본 원인': 'Root cause analysis', '영구 수정': 'Permanent fix', '회고': 'Retrospective',
  '맥락 파악': 'Understand context', '지적 검증': 'Verify findings',
  '영향 범위': 'Impact scope', '훅 작성': 'Write hook', '훅 실행 시험': 'Hook run test', '실세션 확인': 'Live session check',
  '범위 정의': 'Define scope', '스킬 작성': 'Write skill', '계약 테스트': 'Contract test', '연결 확인': 'Connection check',
  // Stages of the pipelines shipped in .claude/pipelines/ (tests/test_pipeline_run.py checks every one has an entry)
  '진단': 'Diagnose', '확인': 'Confirm', '요구사항': 'Requirements', '리뷰-찾기': 'Review-find', '리뷰-확인': 'Review-confirm',
  '초안': 'Draft', '대조': 'Cross-check', '반영': 'Apply', '전체 검증': 'Full verify', 'CI 확인': 'CI check',
  'CHANGELOG 정리': 'CHANGELOG', '배포': 'Publish', '재검사': 'Re-check', '위협 모델 리뷰': 'Threat model review', '태그': 'Tag',
} };
PLG_NAMES.ko = {};   // Korean = the saved title itself
// «Standard templates» card titles (sidereus/pipeline_std.py STD), same lookup rule (48e plgTplShow).
const PLG_TPL_NAMES = { en: {
  '버그 수정': 'Bug fix', '새 기능': 'New feature', '리팩토링': 'Refactoring', '성능 개선': 'Performance', '보안 수정': 'Security fix',
  '의존성 업그레이드': 'Dependency upgrade', '장애 대응': 'Incident response', '리뷰만': 'Review only',
  '훅 변경': 'Hook change', '스킬 작성·변경': 'Skill write · change', '도구·MCP 추가': 'Add tool · MCP',
}, ko: {} };
// Chat room list (92 rcPaint): cards and the open-room strip.
Object.assign(I18N.ko, {
  'Open this room': '이 방 열기', 'No rooms yet.': '아직 방이 없습니다.', 'Back to the room list': '방 목록으로', '← Rooms': '← 방 목록',
  'Select all': '전체 선택', 'Hide': '숨기기', 'Failed': '처리하지 못했습니다',
  // Branch tab (88): unborn HEAD note, known server errors (BR_ERRS)
  'Empty repository': '빈 저장소', 'no commits yet': '아직 커밋이 없습니다',
  'Not a git repository': 'git 저장소가 아닙니다', 'Timed out': '시간이 초과되었습니다',
});
