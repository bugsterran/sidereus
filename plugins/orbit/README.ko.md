# Orbit

Claude Code 계정이 섞이지 않게 해 줍니다. 폴더에 들어가 `claude`를 치면 그 폴더의 계정으로 실행됩니다.
계정 하나는 설정 폴더(`CLAUDE_CONFIG_DIR`) 하나에 대응하고, 셸 함수가 맞는 폴더를 골라 줍니다. 세션이
폴더 매핑과 다른 계정으로 실행되면 세션 시작 훅이 경고합니다(매핑이 없는 폴더에서는 경고하지 않습니다).

## 빠른 시작

1. 플러그인을 설치합니다.
   ```
   /plugin marketplace add bugsterran/orbit
   /plugin install orbit@orbit
   ```
2. `/account add work`로 계정을 추가합니다. 무엇을 만들지(폴더 `~/.claude-work`, 처음이라면 셸 rc 파일의
   런처 블록)를 먼저 보여 주고, 한 번 물은 뒤 실행합니다.
3. 새 셸을 열고 아무 폴더에서나 `claude`를 실행합니다. 그 폴더에서 처음 실행하면 어느 계정을 쓸지 묻고
   답을 기억합니다. 아직 로그인하지 않은 계정이면 `→ work (not signed in yet: type /login)`이 표시됩니다.

## 동작 방식

- 계정마다 설정 폴더가 하나씩 있습니다. `~/.claude`는 기본 계정으로 남고 이름은 `default`입니다.
- `claude`는 셸 함수입니다. `accounts.py resolve`로 현재 폴더에 맞는 계정을 찾아 `CLAUDE_CONFIG_DIR`을
  설정한 다음, 받은 인자를 그대로 넘겨 실제 `claude`를 실행합니다.
- 계정을 고르는 순서는 `claude -A <이름>` > 가장 가까운 폴더 매핑 > `default` 줄 > 계정이 하나뿐이면 그 계정 >
  묻기(터미널에서만) > `~/.claude`입니다. `-A`를 주지 않았다면 직접 export한 `CLAUDE_CONFIG_DIR`이
  우선합니다.
- 물을 때는 «remember for this folder? (Y/n)»이 나오고, Enter를 누르면 기억합니다. `claude -p`나
  터미널이 아닌 곳에서 실행할 때는 묻지 않습니다.
- 셸 블록은 `~/.zshrc` 또는 `~/.bashrc`의 `# >>> folder-accounts >>>`와 `# <<< folder-accounts <<<`
  사이에 들어갑니다. 이 블록은 런처를 불러오고, `FA_PY`가 `~/.local/share/folder-accounts/`에 있는
  `accounts.py` 고정 복사본을 가리키게 합니다. 이 이름들은 Orbit으로 바뀌기 전의 것으로, 기존 설치가
  그대로 동작하도록 바꾸지 않았습니다.
- 세션이 폴더 매핑과 다른 계정으로 실행되면 SessionStart 훅이 경고를 띄웁니다.

## 명령

| 명령 | 설명 |
|---|---|
| `add <이름> [--dir 경로]` | 폴더를 등록합니다(기본값 `~/.claude-<이름>`). 이름은 라벨일 뿐입니다. |
| `add <이름> --copy settings,agents,skills,commands,mcp` | `~/.claude`에서 설정을 복사합니다. 기존 파일은 덮어쓰지 않습니다. |
| `add <이름> --shell` | 셸 블록도 다시 설치합니다(플러그인 업데이트 후). 이 경우에도 `--yes`가 있어야 실제로 씁니다. |
| `rename <옛이름> <새이름>` | 라벨만 바꿉니다. 매핑과 기본값도 함께 바뀌고, 폴더는 그대로입니다. |
| `map [폴더] <이름>` / `unmap [폴더]` | 폴더와 그 하위 폴더에서 쓸 계정을 고정하거나 해제합니다. |
| `default <이름>` | 매핑이 없는 폴더에서 쓸 계정을 정합니다. |
| `list` | 계정, 매핑, 로그인 상태, 등록되지 않은 `~/.claude-*` 폴더를 보여 줍니다. |
| `remove <이름>` | 등록을 해제합니다. 폴더는 지우지 않습니다. |
| `shell install` / `shell uninstall` | rc 블록만 따로 추가하거나 제거합니다. |
| `claude -A <이름>` | 이번 실행에만 계정을 지정합니다. |

`add`와 `shell`은 먼저 dry run 결과를 보여 주고, `--yes`를 붙여야 적용합니다. Claude Code 밖에서는 같은
명령을 `orbit ...`으로 실행합니다(`claude-account`도 별칭으로 동작합니다). 계정마다 `/login`으로 한 번씩
로그인해야 합니다.

## 등록부

등록부는 `~/.claude-accounts`이며, 한 줄에 항목 하나씩 적는 일반 텍스트 파일입니다. 직접 고쳐도 되고,
주석과 알 수 없는 줄은 그대로 보존됩니다.

```
# my accounts
account default ~/.claude
account work ~/.claude-work
map ~/src/acme work
default work
```

## 변경하는 파일

전체 목록은 [SECURITY.md](SECURITY.md)에 있습니다. 요약하면 등록부, 추가한 계정 폴더, rc 파일 안의 표시된
블록 하나(처음 한 번 백업), `accounts.py` 복사본입니다. `.claude.json`은 `oauthAccount` 키가 있는지만
확인합니다. 자격 증명, 키체인, 대화 기록은 읽거나 복사하지 않으며, 네트워크도 사용하지 않습니다.

## 한계

- macOS와 Linux의 zsh, bash에서만 동작합니다. Windows는 지원하지 않습니다.
- 터미널 CLI에서만 동작합니다. 데스크톱 앱과 VS Code 확장은 `CLAUDE_CONFIG_DIR`을 무시합니다
  (claude-code #25762, #30538).
- 플러그인과 마켓플레이스 설정은 일부 무시됩니다(#15071). 플러그인은 계정마다 따로 설치해야 합니다.
  `plugins` 폴더를 계정끼리 공유하면 계정별로 나뉘지 않는 플러그인 캐시도 공유됩니다(예: oh-my-claudecode
  HUD에 다른 계정의 사용량이 보일 수 있습니다).
- 새 계정 폴더는 빈 상태로 시작합니다. `--copy mcp`는 MCP 서버의 `env` 값까지, `--copy settings`는 `env`와
  `apiKeyHelper`까지 복사하므로 토큰이 들어갈 수 있습니다. 두 복사본은 모두 `0600`으로 만듭니다.
- 자격 증명은 복사하거나 바꾸지 않습니다. 계정마다 따로 로그인해야 합니다.
- ⚠ 다른 계정 폴더 입장에서 `~/.claude/CLAUDE.md`는 상위 폴더에 있는 평범한 파일입니다. 그래서 Claude Code가
  홈 아래 모든 폴더에서 이 파일을 프로젝트 `CLAUDE.md`로 읽고 `AGENTS.md`를 건너뜁니다. 해당 계정의
  `settings.json`에 `"claudeMdExcludes": ["/Users/<you>/.claude/CLAUDE.md"]`를 추가하고, 필요한 내용은
  `@import` 대신 계정 폴더에 복사해 두세요(exclude는 import도 막습니다). 이 exclude를
  `~/.claude/settings.json`에 넣으면 안 됩니다. 그러면 기본 계정에서 전역 지침이 빠집니다.

## 다른 도구

| 도구 | 형태 | 폴더별 고정 | 비고 |
|---|---|---|---|
| Orbit | Claude Code 플러그인 + 셸 함수 | 등록부의 `map`. 터미널에서 매핑·기본값이 없고 계정이 둘 이상인 폴더면 한 번 묻고, Enter/Y로 저장 | 그냥 `claude`. 계정 불일치 경고. 자동 전환·대화 기록 공유 없음, 자격 증명을 읽지 않음. |
| [claude-swap](https://github.com/realiti4/claude-swap) | CLI `cswap` + TUI | `cswap map`, `cswap run`에서 사용. 하위 폴더는 가장 가까운 상위 매핑을 따름 | 5시간/7일 한도 근처에서 자동 전환(`cswap auto`, 기본 90%). 선택적 `--share-history`. macOS, Linux, Windows. |
| [claude-code-profiles](https://github.com/quinnjr/claude-code-profiles) | 셸 래퍼 `claude-profile` | `.claude-profile` 파일, 가장 가까운 것 적용, `cd`할 때 전환 | 프로필마다 설정 폴더 하나. |
| [claude-account-switch](https://github.com/ftery0/claude-account-switch) | npm, `CLAUDE_CONFIG_DIR` | 없음. 선택 창 또는 `cpf <이름>` | 명령으로 전환. |
| [claude-account-switcher](https://github.com/ukogan/claude-account-switcher) | 셸 래퍼 + `/switch-profile`, `/whoami` | 없음. `claude <프로필>` 또는 셸 단위 | 설정은 심볼릭 링크로 공유. |
| [claude-switch](https://github.com/SIRTHEO/claude-switch) | npm `@sirtheo/claude-switch` | 저장소에 커밋하는 `.claude-switch`. 이메일 도메인으로 계정을 고를 수 있음 | 저장소 규칙 하나를 팀이 함께 쓰는 용도. |
| direnv / mise | 환경 변수 로더 | `.envrc`에 `export CLAUDE_CONFIG_DIR=~/.claude-work` 한 줄, 또는 `mise.toml`의 `[env]` | 묻기·불일치 경고 없음. |

claude-swap은 여러 계정을 더 많이 쓰게 돕고(순환, 대화 기록 공유), Orbit은 계정을 떼어 둡니다. Orbit과
가장 가까운 것은 claude-code-profiles입니다(`claude()` 래퍼, 기본 프로필, Windows, 스킬 풀까지 있어 지원
플랫폼과 기능이 더 많습니다). Orbit은 폴더 매핑을 등록부 하나(`~/.claude-accounts`)에 두고 프로젝트 폴더에는
아무것도 쓰지 않아, 회사 저장소에 커밋하거나 무시할 파일이 생기지 않습니다. 여기에 세션 시작 시 불일치 경고와
한 번만 묻고 기억하는 프롬프트를 더했고, Claude Code 플러그인으로 설치됩니다. 순환이
필요하면 claude-swap, 팀이 커밋한 저장소 규칙 하나가 필요하면 claude-switch, 이미 direnv나 mise를 쓰고 더
필요한 게 없으면 그것을 쓰세요.

## 업데이트

`/plugin update` 후에는 `orbit shell install --yes`를 한 번 실행하세요. 런처는
`~/.local/share/folder-accounts/`에 있는 `accounts.py` 고정 복사본을 실행하는데, 이 명령을 실행해야 복사본과
rc 블록이 새 버전으로 바뀝니다.

## 제거

먼저 각 계정에서 `/logout`을 실행하세요. 그래야 로그인 정보가 디스크에 남지 않고 해제됩니다.

```
orbit shell uninstall --yes               # 표시된 블록만 지운다
rm ~/.claude-accounts                     # 등록부
rm -r ~/.local/share/folder-accounts      # 고정 복사본
/plugin uninstall orbit@orbit
```

아래 항목은 남아 있으므로 직접 지워야 합니다.

- 계정 폴더(`~/.claude-work` 등). `.credentials.json`, `.claude.json`, 복사한 설정이 들어 있을 수 있습니다.
- 각 계정이 로그인할 때 만든 macOS 키체인 항목 `Claude Code-credentials-*`(키체인 접근에서 지웁니다).
- `~/.zshrc.bak-folder-accounts` / `~/.bashrc.bak-folder-accounts`. 처음 설치하기 전의 rc 사본이라, rc에
  export해 둔 토큰이 들어 있을 수 있습니다.
