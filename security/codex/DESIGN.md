# Codex 데스크톱 연동 설계

이 리포의 보안 조사·레드팀·승인 게이트 흐름을 OpenAI Codex(데스크톱 앱, CLI)에서 구동하기 위한 설계와 그 구현 파일이다.

> **먼저 알아둘 것.** 이 문서의 구성 파일과 실행기는 Codex 공식 문서(2026-11-10 확인, 맨 아래 출처)를 읽고 작성했다. **작성한 환경에 Codex가 없어서 실제 Codex로는 한 번도 실행하지 못했다.** 가짜 `codex` 실행 파일로 실행기가 무엇을 요청하는지는 테스트했지만, 진짜 Codex가 그 요청을 받아 어떻게 동작하는지는 §7의 점검 절차로 직접 확인해야 한다.

## 1. 무엇이 무엇에 대응하나

| 이 리포의 개념 | Codex의 장치 | 파일 |
|---|---|---|
| 조정자의 행동 규칙 | 프로젝트 지시 파일. 리포 루트에서 작업 디렉터리까지의 `AGENTS.md`를 읽는다 | `AGENTS.md` |
| 기본 샌드박스·승인 정책 | 프로젝트 설정. 신뢰한 프로젝트에만 적용된다 | `.codex/config.toml` |
| 헌터·비평가·체인 조사자 | 커스텀 서브에이전트 (`name`, `description`, `developer_instructions`) | `.codex/agents/*.toml` |
| 반복 작업 절차 | 스킬. `.agents/skills/<이름>/SKILL.md` | `.agents/skills/` |
| "승인은 사람만" | 명령 규칙(`prefix_rule`) + 도구 자체의 터미널 확인 | `.codex/rules/security.rules`, `verify.py` |
| 30명 이상 라운드 | 에이전트마다 `codex exec` 프로세스 하나 | `security/redteam/codex_round.py` |
| 공유 보드, 팀 계획, 체인 계획 | 그대로. Codex와 무관한 표준 라이브러리 도구 | `security/redteam/*.py` |
| PoC 실행 샌드박스 | 그대로. Codex 샌드박스와 별개의 층 | `security/pipeline/verify.py` |

## 2. 처음 설정

1. Codex 데스크톱 앱에서 이 리포 폴더를 프로젝트로 연다.
2. 프로젝트를 **신뢰함**으로 표시한다. `.codex/` 아래의 설정·규칙은 신뢰한 프로젝트에서만 적용된다.
3. Codex를 재시작한다. 규칙과 스킬은 시작할 때 읽힌다.
4. 권한 선택은 **Ask for approval** 또는 **Custom (config.toml)** 을 쓴다. **Full access는 쓰지 않는다** — 샌드박스와 승인이 모두 꺼진다.
5. §7의 점검을 한 번 돌린다.

## 3. 쓰는 방법

### 3.1 상태 확인 — `$security-status`

후보의 승인 상태, 체인 가설, 보류된 커버리지, 테스트 결과를 보고한다. 읽기와 도구 실행뿐이라 암묵적으로도 호출된다("조사 상태 알려줘").

### 3.2 PoC 하네스 작성 — `$poc-harness`

후보 하나의 하네스를 계약에 맞춰 쓰고 **실행하지 않는다**. 문법 검사만 하고, 소유자가 직접 실행할 승인 명령을 보여 주고 멈춘다. 명시적으로 불렀을 때만 동작한다.

### 3.3 레드팀 라운드 — `$redteam-round`

명시적으로 불렀을 때만 동작한다. 먼저 팀 계획을 만들어 규모와 비용 추정을 보여 주고, **확인을 받은 뒤** 시작한다. 규모에 따라 두 경로로 갈린다.

| | 스레드 안 서브에이전트 | 별도 프로세스 (`codex_round.py`) |
|---|---|---|
| 규모 | 6명 이하 | 7명 이상, 30명 이상 라운드 |
| 어디서 시작 | 데스크톱 앱 스레드 | **터미널** |
| 쓰기 격리 | 지시로만. 서브에이전트는 부모의 샌드박스를 그대로 물려받는다 | Codex 샌드박스가 강제. 에이전트마다 작업 디렉터리가 자기 scratch뿐이다 |
| 진행 확인 | 앱의 서브에이전트 목록 | 실행 디렉터리의 로그와 `round-<n>-status.json` |
| 읽히는 지시 파일 | 루트 `AGENTS.md` | scratch의 규칙 파일. 실행 디렉터리가 리포 안이면 루트 `AGENTS.md`도 함께 |
| `baselines/` 안의 지시 파일 | 읽히지 않는다 | 읽히지 않는다 |

```bash
python3 security/redteam/teamplan.py plan --target . --max-team 40 --out .redteam-runs/r1/plan.json
```

```bash
python3 security/redteam/codex_round.py run --plan .redteam-runs/r1/plan.json --run-dir .redteam-runs/r1 --dry-run
```

```bash
python3 security/redteam/codex_round.py run --plan .redteam-runs/r1/plan.json --run-dir .redteam-runs/r1 --model <선택한 모델>
```

실행 디렉터리 `.redteam-runs/`는 git이 무시한다. 통째로 커밋하지 않는다.

### 3.4 예약 작업

데스크톱 앱의 예약 작업에는 `security-status`만 붙이는 것을 권한다. 예약 작업은 사람이 지켜보지 않는 상태로 기본 샌드박스 설정에서 돈다. 라운드 시작이나 푸시를 예약하지 않는다.

## 모델: 스웜 전체가 한 가지 모델

스웜은 **선택한 모델 하나를 여러 개 띄우는 방식**이다. 역할별로 다른 모델을 섞지 않는다.

| 경로 | 어떤 모델로 도는가 | 어떻게 고정했나 |
|---|---|---|
| 스레드 안 서브에이전트 | 그 스레드에서 선택한 모델. Codex의 서브에이전트는 따로 지정하지 않으면 부모의 모델을 상속한다 | `.codex/agents/*.toml`에 `model`이 없고, `.codex/config.toml`에 `model`·`agents.default_subagent_model`이 없다. 스킬은 띄울 때 모델을 지정하지 말라고 지시한다 |
| 별도 프로세스 (`codex_round.py`) | `--model`로 준 모델 하나. 생략하면 전원이 Codex 설정의 기본 모델 | 실행기가 같은 값을 모든 에이전트에 넘긴다. 계획 파일의 에이전트 항목에 `model`·`profile` 등이 있으면 실행을 거부한다 |

- 별도 프로세스는 데스크톱 스레드에서 고른 모델을 **알지 못한다.** 스레드의 선택과 맞추려면 그 모델 이름을 `--model`로 한 번 넘겨야 한다. 스킬은 이름을 추측하지 않고 사용자에게 묻는다.
- 추론 강도(reasoning effort)도 에이전트별로 지정하지 않는다. 스레드 안에서는 부모 설정을, 별도 프로세스에서는 Codex 설정의 기본을 따른다.
- 이 정책은 테스트로 고정했다. 커스텀 에이전트 파일이나 프로젝트 설정에 모델 지정이 들어오면 `security/redteam/tests/test_codex_config.py`가 실패한다.
- 스레드 안에서 조정자가 서브에이전트를 띄우며 모델을 직접 지정하는 것까지 막는 기술적 장치는 없다. 그 부분은 지시에 기댄다.

## 4. 별도 프로세스 실행기가 하는 일

에이전트 하나당 아래 명령을 띄운다.

```
codex exec --color never --skip-git-repo-check
           --sandbox workspace-write
           -C <run>/agents/<id>/scratch
           --output-last-message <run>/agents/<id>/scratch/last-message.txt
           -c sandbox_workspace_write.network_access=false
           -                                   (프롬프트는 표준 입력으로)
```

- **작업 디렉터리 = 그 에이전트의 scratch.** `workspace-write` 샌드박스는 작업 디렉터리 밖 쓰기를 막으므로, 보드 설계의 "자기 outbox에만 쓴다"가 규칙이 아니라 강제가 된다. 읽기는 막지 않으므로 대상 리포와 다른 에이전트의 outbox는 읽을 수 있다.
- **작업 디렉터리가 `baselines/`나 `benchmarks/`가 아니다.** Codex는 프로젝트 루트에서 작업 디렉터리까지의 경로 위에서만 지시 파일을 찾으므로, 조사 대상 안의 `AGENTS.md`·스킬은 지시로 읽히지 않는다. 실행기는 scratch에 규칙 파일(`AGENTS.md`)을 만들어 넣는다. 실행 디렉터리를 리포 안(`.redteam-runs/`)에 두면 이 리포의 루트 `AGENTS.md`와 `.codex/` 설정도 함께 적용되고, 리포 밖에 두면 scratch의 규칙 파일만 적용된다.
- **네트워크 끔.** `workspace-write`의 기본이 꺼짐이고, 사용자 설정이 켜 두었더라도 끄도록 설정 덮어쓰기를 넘긴다.
- **`--add-dir`, `danger-full-access`, 승인 우회 플래그는 쓰지 않는다.** 테스트가 이것을 확인한다.
- 단계는 사냥 → 비평 → 체인 순이고, 각 단계는 계획의 동시 실행 상한 크기로 나뉜다. 단계가 끝날 때마다 보드를 병합한다.
- 에이전트별 결과는 `ok` / `failed` / `timeout` / `no_result` / `bad_json` / `launch_failed`로 구분해 `round-<n>-status.json`에 남긴다. 실패한 에이전트를 숨기지 않는다.
- 시간 초과한 프로세스는 프로세스 그룹째 종료한다.

**터미널에서 시작해야 하는 이유.** 데스크톱 스레드는 네트워크가 꺼진 샌드박스 안에서 명령을 실행한다. 거기서 실행기를 돌리면 자식 Codex 프로세스가 모델에 연결하지 못한다. 그래서 스킬은 계획과 드라이런까지만 하고 실제 실행 명령은 사용자에게 넘긴다. Full access를 요청해 우회하지 않는다.

## 5. 샌드박스와 승인: 세 층

| 층 | 막는 것 | 누가 통제 |
|---|---|---|
| Codex 샌드박스 | 에이전트의 명령이 작업 영역 밖을 쓰거나 네트워크에 나가는 것 | Codex. `.codex/config.toml` |
| 파이프라인 샌드박스 | **PoC 하네스**가 네트워크·자격 증명·대상 쓰기에 닿는 것 | `verify.py` (docker 또는 unshare) |
| 승인 게이트 | 승인 없이 하네스가 실행되는 것 | 소유자. `approvals.json`이 `main`에 커밋돼야 한다 |

세 층은 서로를 대신하지 않는다. Codex 샌드박스가 켜져 있어도 PoC는 파이프라인 샌드박스 안에서만 돈다.

### 승인을 에이전트가 하지 못하게

1. **`AGENTS.md`** 가 금지한다(지시).
2. **명령 규칙**이 `python3 security/pipeline/verify.py approve`를 `forbidden`으로 막고, `verify.py run`·`codex_round.py run`·`git push`는 `prompt`로 사람에게 묻는다.
3. **`verify.py approve` 자체**가 대화형 터미널이 아니면 거부하고, 터미널에서는 fingerprint를 다시 입력해야 기록한다. 에이전트가 실행하는 명령에는 터미널이 없다.
4. **GitHub 쪽**: 워크플로는 `main`의 `approvals.json` 변경에만 반응하고 실행 주체가 리포 소유자인지 확인한다.

1~3은 **실수를 막는 장치이지 경계가 아니다.** 규칙은 인자 접두사가 정확히 일치해야 걸리므로 `./security/pipeline/verify.py`처럼 표기만 바꿔도 빠져나간다(모의 검사로 확인). 터미널 확인도 의사 터미널로 우회할 수 있고, 소유자 계정으로 도는 에이전트는 JSON 파일을 직접 고칠 수도 있다. 실제로 기대는 통제는 **소유자가 `approvals.json` 커밋을 직접 보는 것**이다.

에이전트에게 푸시 권한을 맡길 생각이라면 GitHub Settings → Environments에서 `poc-approval` 환경에 required reviewers를 지정해 두는 것을 권한다. 그러면 워크플로의 하네스 실행 작업이 GitHub 화면에서의 사람 승인을 기다린다.

### PoC 실행은 어디서

`verify.py`의 로컬 백엔드 `unshare`는 Linux 전용이다. macOS에서는 Docker가 필요하고, Codex 샌드박스 안에서는 Docker 소켓에 닿지 못할 가능성이 높다. 그 경우 `verify.py`는 `blocked`로 끝나고 아무것도 실행하지 않는다. 그래서 Codex 데스크톱에서의 권장 경로는 **승인 커밋 → GitHub Actions 워크플로**다.

## 6. 대상 리포 안의 지시 파일

조사 대상인 `baselines/`에는 `AGENTS.md`(CodeEvolve), `CLAUDE.md`(OpenEvolve), 스킬 4개(ShinkaEvolve)가 들어 있다. 에이전트에게 지시로 읽히면 안 되는 파일들이다.

- Codex는 프로젝트 루트에서 **작업 디렉터리까지 내려가는 경로 위의** `AGENTS.md`만 읽는다. 작업 디렉터리가 리포 루트면 `baselines/CodeEvolve/AGENTS.md`는 읽히지 않는다. **`baselines/` 안으로 들어가서 Codex를 시작하지 않는다.**
- 스킬은 `.agents/skills`에서만 찾는다. `baselines/ShinkaEvolve/skills/`는 그 경로가 아니다.
- `CLAUDE.md`는 Codex의 기본 지시 파일 이름이 아니다. `project_doc_fallback_filenames`에 추가하지 않는다.
- 별도 프로세스 실행기에서는 작업 디렉터리가 에이전트의 scratch라서 `baselines/` 안의 파일은 어느 것도 경로 위에 없다.
- 그래도 에이전트가 조사하면서 그 파일들을 **읽기는** 한다. 읽은 내용을 지시로 따르지 않게 하는 것은 `AGENTS.md`와 에이전트 규칙 파일의 문장이고, 이것은 지시일 뿐 강제가 아니다.

## 7. 처음 한 번 직접 확인할 것

Codex가 설치된 머신에서 순서대로 돌린다. 하나라도 기대와 다르면 그 단계에서 멈추고 설정을 고친다.

1. 규칙이 읽히고 의도대로 판정하는가. 기대: `forbidden`.

   ```bash
   codex execpolicy check --pretty --rules .codex/rules/security.rules -- python3 security/pipeline/verify.py approve x --by y
   ```

2. 지시 파일이 읽히는가. 기대: 루트 `AGENTS.md`의 규칙을 인용하고, `baselines/` 안의 지시 파일 내용은 나오지 않는다.

   ```bash
   codex exec --sandbox read-only "Summarize the current instructions."
   ```

3. 실행기가 만드는 명령과 프롬프트를 본다(아무것도 시작하지 않는다).

   ```bash
   python3 security/redteam/codex_round.py run --plan security/redteam/plans/round-1.json --run-dir .redteam-runs/check --dry-run
   ```

4. 에이전트 **한 명만** 실제로 돌린다. 기대: 상태 `ok`, scratch 밖에 새 파일이 없고(`git status`가 깨끗), `codex.stderr.log`에 설정 오류가 없다.

   ```bash
   python3 security/redteam/codex_round.py run --plan security/redteam/plans/round-1.json --run-dir .redteam-runs/check --phase hunt --only r1-h001-seam-program-stdout-to-score
   ```

   Codex가 `-c sandbox_workspace_write.network_access=false`를 거부하면 `--no-network-override`를 붙인다.

5. 데스크톱 앱에서 스킬 3개가 보이는지, `$security-status`가 동작하는지 확인한다.

6. 그다음에 작은 라운드(`--max-team 10` 정도)를 돌리고, 문제가 없으면 늘린다.

## 8. 검증되지 않은 것

| 항목 | 상태 |
|---|---|
| `codex_round.py` | 가짜 `codex`로 테스트 15개 통과: 플래그, 작업 디렉터리, 단계 순서, 상태 구분, 시간 초과 종료. **실제 Codex로는 미실행** |
| `.codex/config.toml`, `.codex/agents/*.toml` | TOML 문법과 문서에 나온 키 이름만 확인. Codex가 실제로 받아들이는지 미확인 |
| `.codex/rules/security.rules` | 문서의 접두사 매칭 의미를 흉내 낸 검사로 인라인 예시 통과. Codex 로더로는 미확인. 규칙 기능은 Codex 문서상 실험적이다 |
| 스킬 3개 | 머리말 형식만 확인. 실제 호출 미확인 |
| `workspace-write`가 작업 디렉터리 밖 쓰기를 실제로 막는가 | 문서 근거. 직접 관찰하지 못했다. §7의 4번에서 확인 |
| 서브에이전트 동시 실행 상한 | 문서에 기본값이 없다. 프로젝트 설정에서 6으로 잡았다 |
| 서브에이전트가 부모 모델을 상속하는가 | 문서 근거. 실제 Codex에서 서브에이전트가 어떤 모델로 도는지는 관찰하지 못했다 |
| 데스크톱 앱이 CLI와 같은 규칙으로 `AGENTS.md`를 찾는가 | 문서가 명시하지 않는다 |
| Windows | 고려하지 않았다 |
| 30명 이상 동시 실행 | 계정의 속도 제한·요금에 달려 있다. 시도하지 않았다 |

## 출처

- [Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode) — `codex exec`, 기본 읽기 전용 샌드박스, 표준 입력 프롬프트, `-o`
- [Developer commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli) — `--sandbox`, `-C`, `--add-dir`, `-c`, `--skip-git-repo-check`
- [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) — 커스텀 에이전트 파일, 부모 샌드박스 상속, 동시 실행 상한 키, 데스크톱 표시
- [Build skills](https://learn.chatgpt.com/docs/build-skills) — 스킬 위치, 머리말, `agents/openai.yaml`
- [Custom instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) — 루트에서 작업 디렉터리까지의 탐색, 32 KiB 한도
- [Sandboxing](https://learn.chatgpt.com/docs/sandboxing) — 샌드박스 모드, 승인 정책, 데스크톱 권한 선택지
- [Rules](https://learn.chatgpt.com/docs/agent-configuration/rules) — `prefix_rule` 문법, 판정 우선순위, 한계
- [Scheduled tasks](https://developers.openai.com/codex/app/automations) — 예약 작업
