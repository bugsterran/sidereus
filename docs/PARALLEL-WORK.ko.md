# 병렬 작업 공간

[English](PARALLEL-WORK.md) · **한국어**

브랜치 탭은 여러 브랜치를 worktree 와 세션 하나씩으로 동시에 돌리는 명령을 만들어 준다.
시데레우스는 명령을 클립보드에 복사만 하고, 실행은 터미널에서 직접 한다.

## 원칙

- 시데레우스는 셸·git·세션을 직접 돌리지 않는다. 세션은 Claude Code 가 띄우고(`claude -w <이름> --tmux` 가 worktree 생성, 세션 시작, tmux/iTerm2 창까지 한다) 시데레우스는 지켜본다.
- ⚠ 페이지에서 프로세스를 띄우는 엔드포인트는 두지 않는다. Host·Origin 검사가 있어도 로컬 HTTP 가 원격 코드 실행 경로가 된다.
- ⚠ checkout·merge·rebase·push 는 넣지 않는다. 돌고 있는 에이전트의 작업 폴더를 바꿔 버린다. 터미널이나 Claude 로 한다.

## 순서

| 단계 | 내가 하는 일 | 시데레우스 |
|---|---|---|
| 시작 | «＋ 병렬 작업» 에 이름을 넣고 명령을 터미널에 붙여 넣는다 | `git worktree add … && claude`(아래 참고) 또는 `claude -w <이름> --tmux` |
| 진행 | 창마다 일을 시킨다 | worktree 카드(세션, 5시간 점유, 미커밋, 앞섬/뒤짐), 주의 목록, «충돌 위험» |
| 합치기 | 터미널이나 Claude 로 merge 하거나 PR 을 연다 | 카드의 기준 대비 «↑N», 커밋마다 세션과 비용 |
| 정리 | 정리 명령을 붙여 넣는다 | `git -C <repo> worktree remove <경로>` |

## git-flow

폼 기본값은 git-flow 다. 접두사와 develop/master 이름은 `git flow init` 설정(`gitflow.*`)을 따르고, 없으면 아래 기본값을 쓴다.

| 종류 | 브랜치 | 기준 | 카드 비교 대상 · PR 대상 |
|---|---|---|---|
| feature | `feature/<이름>` | develop | develop · develop |
| bugfix | `bugfix/<이름>` | develop | develop · develop |
| release | `release/<이름>`(예: `1.4.0`) | develop | master · master + develop |
| hotfix | `hotfix/<이름>` | master | master · master + develop |

```sh
git -C '<repo>' worktree add '<repo>.wt/<type>-<name>' -b '<branch>' '<base>' && cd '<folder>' && claude
```

- ⚠ 로컬 develop 이 없으면 master 에서 가르고 폼에 «develop 없음 — <master> 에서 가릅니다» 가 뜬다.
- develop·master 가 원격에만 있으면 `--no-track` 을 붙이고 «로컬 브랜치 없음 — 원격 <기준> 에서 가릅니다» 가 뜬다.
- «claude -w 로 (HEAD 에서)» 는 git-flow 를 안 쓰는 저장소용이다. `cd '<repo>' && claude -w <이름> --tmux` 를 만든다.

## 폼과 정리

- «＋ 병렬 작업» 은 저장소 칩 옆에 있다. 이름 칸 하나와 복사 버튼이다.
- ⚠ 이름은 `[a-z0-9._-]` 이고 영소문자나 숫자로 시작해야 한다. `.` 로 시작하거나 끝나는 이름, `..`, `.lock` 은 안 된다. 붙여 넣은 명령을 셸이 해석하므로 다른 문자는 복사 자체를 막는다.
- 이미 있는 worktree·브랜치 이름이면 경고가 뜨지만 복사는 된다.
- «정리 명령» 은 세션이 없는, main 이 아닌 worktree 카드에만 뜬다.
- ⚠ `--force` 는 넣지 않는다. 미커밋 파일이 있으면 카드에 «미커밋 N — 지우면 사라진다» 가 뜨고, git 이 삭제를 거부한다.

## 넣지 않은 것

| 기능 | 이유 |
|---|---|
| 페이지에서 명령 실행 | 원격 코드 실행 경로 |
| 작업마다 worktree 자동 생성, 에이전트 선택 UI | Orca(stablyai/orca)·Conductor 가 하는 일 |
| 커밋 검색, blame, 브랜치 비교 | GitKraken 과 터미널이 한다 |

시데레우스가 더하는 것은 세션을 어떻게 띄웠든(`claude -w`, Orca, 직접 만든 worktree) 가로질러 보는 화면이다.
worktree 별 할당량 점유, 나를 필요로 하는 세션, 세션 간 충돌 경고, 공용 메일박스.

코드: `web/js/89-branch-worktree.js`(`brPw*`, `brWrmHtml`, `brWtHtml`, `brWtMeta`), `sidereus/git_wt.py` `wt_signals`.
