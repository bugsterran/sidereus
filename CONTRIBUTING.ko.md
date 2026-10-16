# 기여하기

[English](CONTRIBUTING.md) · **한국어**

시데레우스는 개인 도구이고, 있는 그대로 공유한다. 지원·로드맵 약속은 없다. 방향은 작성자가 정한다.

대부분은 코드 없이 설정 › «내 방식» 과 `config.local.json` 으로 된다 — [바꾸는 법](README.ko.md#설정-바꾸기) · [docs/CONFIG.ko.md](docs/CONFIG.ko.md).

## 받는 것

| 구분 | 무엇 | 방법 |
|---|---|---|
| 버그 신고 | 환영 | 재현 절차를 적은 이슈. 대화 내용이 화면에 실리는 문제가 아닌지(메타데이터만) 확인한다. |
| 확장 PR | 받음 | 구조 언어 플러그인(`sidereus/structure_lang_*.py`, `lang_register`) · CLI 어댑터(`sidereus/plat_codex.py` 같은 플랫폼 리더) · 파이프라인 템플릿(`.claude/pipelines/*.json`). |
| 코어 PR | 받지 않음 | 서버, UI, state 형태. 이쪽은 **포크한다**. |

이유: 확장은 공유 형식에 꽂히므로 포크끼리 호환이 유지된다.

확장 PR 은 이 문서와 [docs/EXTENDING.ko.md](docs/EXTENDING.ko.md) 만 따르면 된다. `AGENTS.md` 는 작성자 자신의 에이전트 작업 규칙(동시 편집 규약 · 파이프라인 단계)이라 지키지 않아도 된다.

확장 문서: [docs/EXTENDING.ko.md](docs/EXTENDING.ko.md) (함께: [docs/ARCHITECTURE.ko.md § 8](docs/ARCHITECTURE.ko.md#확장) · [docs/STRUCTURE.ko.md](docs/STRUCTURE.ko.md)).

## PR 과 AI 도움

코드를 만드는 비용은 싸졌고 리뷰 비용은 그대로다(James Ross, "Open source as we knew it is dead" 참고). 그래서:

- AI 도움을 받아 썼는지 밝힌다(PR 템플릿의 체크박스). 어느 쪽이든 괜찮지만 밝히지 않는 것은 안 된다.
- PR 이 고치는 실패 테스트나 재현 절차를 함께 낸다. 없으면 리뷰 없이 닫는다.
- 어댑터 PR 은 어댑터 계약 테스트를 통과한 뒤에만 리뷰한다: `bash tests/run.sh -p test_adapter_contract.py`(`tests/test_adapter_contract.py`).
- PR 하나에 변경 하나. 작게 유지한다.

## 확장 PR 점검표

- `bash scripts/check.sh --fast` 통과.
- 테스트는 만든 입력으로, 1초 안에 끝난다. 라이브 파일·시계·네트워크를 쓰지 않는다.
- 메타데이터만 — 대화 내용·도구 입력을 페이지나 MCP 답에 싣지 않는다.
- 주석은 영어.
- 새 의존성 없음(표준 라이브러리만, 오프라인 동작).

## 포크에서 게이트 돌리기

```sh
bash scripts/check.sh --fast   # py_compile(/usr/bin/python3, 3.9) + node --check + 유출 검사
bash scripts/check.sh --full   # 단위 테스트와 화면 검사까지
bash tests/run.sh              # 단위 테스트만
```

- ⚠`/usr/bin/python3`(3.9)을 쓴다 — launchd 가 이것으로 뷰어를 돌린다. 새 Python 으로 통과시키면 3.9 에 없는 문법이 새어 들어간다. 테스트는 라이브 파일·시계·네트워크를 쓰지 않는다.

## 메타데이터만 보장을 유지하려면 지킬 것

- 대화 내용·도구 입력을 페이지나 MCP 답에 싣지 않는다 — 경로, 세션 id, 모델, 상태, 개수, 시각만. 예외는 클릭해야 열리는 작업 팝업(`sidereus/work.py`) 하나다.
- 루프백 전용. 모든 POST 에 Host/Origin 가드를 둔다. `innerHTML` 에 넣는 값은 `esc()` 한다.
- git 쓰기·CLI 제어(pty, send-keys, spawn/kill) 없음. git 호출은 `git_argv` 를 거친다.
- 표준 라이브러리만. 오프라인에서 돌아야 한다.
- 시데레우스가 하지 않는 일과 각각의 끄는 스위치: [SECURITY.ko.md](SECURITY.ko.md).
