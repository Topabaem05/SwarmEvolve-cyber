# 승인 게이트 PoC·재현 검증 파이프라인 설계

후보(candidate)는 소스 분석만으로 만든다. PoC 실행과 재현 검증은 **리포 소유자가 승인한 뒤에만**, 격리된 샌드박스에서 자동으로 수행한다. 이 문서는 그 구조와 근거를 설명한다.

## 1. 단계와 상태

```
 조사 (자동, 실행 없음)             승인 (사람)                 검증 (자동, 샌드박스)            확정 (사람 + 독립 검증)
┌──────────────────────────┐   ┌─────────────────────┐   ┌──────────────────────────┐   ┌─────────────────────────┐
│ 도구 5종 + 소스 분석     │   │ 하네스 리뷰          │   │ 네트워크 없는 컨테이너   │   │ 증거 검토               │
│ → findings.json          │──▶│ verify.py approve    │──▶│ exploit ×3 + control ×1  │──▶│ findings.json 판정 갱신 │
│   (needs_validation)     │   │ approvals.json 커밋  │   │ → evidence/result.json   │   │ (confirmed / rejected)  │
└──────────────────────────┘   └─────────────────────┘   └──────────────────────────┘   └─────────────────────────┘
        candidate                     approved              reproduced | not_reproduced
                                                            | inconclusive | blocked
```

| 상태 | 의미 | 누가 바꾸는가 |
|---|---|---|
| `needs_validation` | 소스 추적은 완결됐고 로컬 관찰만 남은 후보. 심각도 없음 | 조사 단계 |
| `approved` | 소유자가 이 후보의 하네스 실행을 승인함 | 소유자 (`approvals.json` 커밋) |
| `reproduced` | exploit 실행 전부에서 관찰되고 control 실행에서는 관찰되지 않음 | 러너 |
| `not_reproduced` | exploit 실행 어디에서도 관찰되지 않음 | 러너 |
| `inconclusive` | 하네스 오류·타임아웃·실행 간 불일치, 또는 control에서도 관찰됨 | 러너 |
| `blocked` | 승인 없음/만료, 하네스 없음, 샌드박스 통제 미성립, 의존성 없음 | 러너 |
| `confirmed` / `rejected` | 최종 판정. `confirmed`에만 심각도를 부여 | 독립 검증자 + 소유자 |

러너는 `reproduced`까지만 기록한다. `findings.json`의 판정을 `confirmed`로 올리는 것은 자동화하지 않았다. 재현됐다는 사실과 "경계를 넘는 의미 있는 영향이 있다"는 판단은 별개이고, 후자는 증거를 읽은 사람이 내려야 한다.

## 2. 승인

### 무엇이 승인인가

`security/approvals/approvals.json`에 항목이 있고, 그 파일이 **기본 브랜치(`main`)에 커밋**되어 있는 것. 기본 브랜치에 쓸 수 있는 사람만 승인할 수 있다.

```bash
python3 security/pipeline/verify.py approve <fingerprint> --by <github-login>
```

```bash
git add security/approvals/approvals.json && git commit -m "security: approve PoC for <fingerprint>" && git push origin main
```

### 승인은 리뷰한 내용에 결박된다

승인 항목에는 세 가지 해시가 들어간다.

| 필드 | 대상 | 바뀌면 |
|---|---|---|
| `harness_sha256` | `security/pipeline/poc/<slug>/`의 모든 파일 | 승인 후 하네스를 고치면 실행 안 됨 |
| `candidate_sha256` | `candidates.json`의 해당 후보 기록 | 후보 주장이 바뀌면 실행 안 됨 |
| `cited_files_sha256` | 후보가 인용한 대상 소스 파일들 | 대상 코드가 바뀌면 실행 안 됨 |

셋 중 하나라도 현재 값과 다르면 상태는 `stale`이고 러너는 실행하지 않는다(`blocked: approval_stale`). 승인받은 뒤 하네스를 다른 코드로 바꿔치기하는 경로를 막기 위한 것이다. 하네스가 없는 후보는 승인 자체가 거부된다 — 승인은 "이 정확한 코드를 실행해도 된다"는 뜻이어야 하기 때문이다.

철회는 항목에 `"revoked": true`를 넣거나 항목을 지우고 커밋한다.

### 승인 후 자동 실행

`.github/workflows/security-poc-verify.yml`이 `main`의 `approvals.json` 변경 푸시에 반응한다.

1. **gate** — `github.actor == github.repository_owner`가 아니면 여기서 끝난다. 게이트 로직 단위 테스트를 돌리고 승인된 후보 수를 센다. 0이면 이후 작업을 건너뛴다.
2. **verify** — 샌드박스 이미지를 빌드하고(이때만 네트워크 사용, 하네스는 실행하지 않음), 자체 점검으로 통제를 확인한 뒤, 승인된 하네스를 실행한다. 이 작업의 토큰 권한은 `contents: read`뿐이다.
3. **record** — 별도 작업이 증거 아티팩트를 받아 검증한 뒤 `security-evidence` 브랜치에 커밋한다. 쓰기 권한은 이 작업에만 있고, 이 작업은 하네스를 실행하지 않는다.

선택적 2차 게이트: 리포 Settings → Environments에서 `poc-approval` 환경에 required reviewers를 지정하면 `verify` 작업이 리뷰어 승인을 기다린다. 지정하지 않으면 1차 게이트(승인 커밋)만 적용된다.

로컬에서도 같은 러너를 쓴다.

```bash
python3 security/pipeline/verify.py run --all-approved
```

### 이 워크플로에 넣으면 안 되는 것

`pull_request`, `pull_request_target`, `issue_comment`, `workflow_run` 트리거. 이 워크플로는 PoC 코드를 실행하므로 쓰기 권한이 없는 사람이 시작할 수 있는 이벤트가 하나라도 있으면 안 된다. (조사 중 벤더링된 OpenEvolve의 `claude.yml`이 바로 이 유형으로 검토됐다. 이 리포에서는 비활성이라 기각했다.)

## 3. 샌드박스

하네스는 아래 통제가 **이번 실행에서 실제로 성립한 경우에만** 실행된다. 하나라도 확인되지 않으면 `blocked`로 끝난다(fail-closed).

| 통제 | docker 백엔드 (CI) | unshare 백엔드 (로컬, Docker 없을 때) |
|---|---|---|
| 외부 네트워크 없음 | `--network none` | 새 네트워크 네임스페이스. `/proc/net/dev`에 `lo` 외 인터페이스가 있으면 중단 |
| 빈 허용목록 환경 | `-e`로 7개 변수만 | `env -i` + 같은 7개 변수 |
| 대상 읽기 전용 | `-v repo:/target:ro`, `--read-only` 루트 | 모든 마운트를 ro로 재마운트한 뒤 대상·`/tmp`·홈 등에 쓰기 프로브. 하나라도 써지면 중단 |
| scratch에만 쓰기 | `-v scratch:/scratch:rw`, `/tmp`는 64 MB tmpfs | scratch만 rw 바인드 |
| 권한 축소 | uid 65534, `--cap-drop ALL`, `no-new-privileges` | `setpriv --bounding-set=-all --no-new-privs` |
| CPU·메모리·파일 크기 | `--cpus 1`, `--memory`, `--ulimit` | `prlimit --cpu --as --fsize` |
| 프로세스 수 | `--pids-limit` | PID 네임스페이스 + `--kill-child` (개수 제한 없음) |
| 벽시계 시간 | `timeout` + 러너 타임아웃 | 동일 |

환경 변수 허용목록: `PATH`, `LANG`, `HOME`, `TMPDIR`, `PYTHONDONTWRITEBYTECODE`, `PYTHONNOUSERSITE`, `PYTHONHASHSEED`. 호스트 환경은 전달되지 않으므로 API 키 같은 자격 증명이 하네스에 닿지 않는다.

**unshare 백엔드의 한계.** 컨테이너보다 약하다. seccomp가 없고, 호스트와 커널을 공유하며, 프로세스 수 제한이 없다. Docker가 없는 환경에서 쓸 수 있는 차선책이고, CI는 docker 백엔드를 쓴다.

`verify.py selftest`는 대상 코드를 건드리지 않는 하네스로 네트워크 차단, 최소 환경, 읽기 전용 대상, scratch 쓰기를 샌드박스 **안에서** 확인한다.

## 4. 하네스 계약

`security/pipeline/poc/<slug>/` (`<slug>`는 fingerprint에서 `[A-Za-z0-9._-]` 외 문자를 `_`로 바꾼 것)

- `poc.py` — `python -I poc.py --mode exploit|control --target <repo> --scratch <dir>`로 호출된다.
- `poc.json` — 관찰 대상 설명, `control` 사용 여부, 제한값 조정.

규칙:

1. **더미 데이터만.** 실제 자격 증명, 외부 호스트, 실제 사용자 데이터를 쓰지 않는다.
2. **최소 효과에서 멈춘다.** 경계가 넘어갔음을 보이는 관찰 하나(scratch의 마커 파일, 응답 본문의 센티널 문자열 등)가 나오면 끝이다. 지속성, 은닉, 영향 확대는 하지 않는다.
3. **control 모드가 있다.** 같은 경로를 무해한 입력으로 실행해 관찰이 나타나지 않음을 보인다. control에서도 관찰되면 그 관찰은 취약점을 구별하지 못하는 것이므로 `inconclusive`다.
4. **결과는 stdout 한 줄.** `POC_RESULT {"observed": true|false, "detail": ...}`. 종료 코드 0 = 관찰됨, 3 = 관찰 안 됨, 4 = 의존성 없음. 결과 줄과 종료 코드가 어긋나면 하네스 오류로 처리한다.
5. **scratch 밖에 쓰지 않는다.** 러너는 scratch에서 아무것도 꺼내오지 않는다. 증거는 러너가 캡처한 stdout/stderr(각 64 KiB 상한)뿐이다.

판정: exploit 3회 모두 관찰 + control 0회 관찰 → `reproduced`. 3회 모두 미관찰 → `not_reproduced`. 그 외 → `inconclusive`.

## 5. 증거

`security/evidence/<slug>/<UTC 시각>/result.json` 한 파일. 들어가는 것: fingerprint, 대상 커밋, 결박 해시 3종, 승인 상태, 백엔드와 이미지, 제한값, 허용 환경 변수 **이름**, 시도별 모드·종료 코드·결과·캡처된 출력, 판정과 사유.

CI에서는 `collect_evidence.py`가 아티팩트를 디렉터리 트리로 신뢰하지 않고, 정해진 경로의 `result.json`만, 일반 파일이고 2 MiB 이하이며 러너가 쓰는 필드를 가진 JSON일 때만 받아 다시 직렬화해 저장한다.

## 6. 하네스가 아직 없는 후보

조사 단계는 후보마다 `validation_plan.local`(무엇을 구동하고 무엇을 관찰할지)을 남긴다. 하네스 코드는 그 계획을 구현한 것이고, 작성 → 리뷰 → 승인 → 실행 순서를 따른다. 하네스 작성 자체는 실행이 아니므로 승인 없이 PR로 올릴 수 있지만, 실행은 승인 이후다.

## 7. 이 설계가 막으려는 것

| 위험 | 대응 |
|---|---|
| 승인 없이 PoC가 실행됨 | 러너가 승인 없으면 `blocked`. 단위 테스트로 고정 |
| 승인 후 하네스 바꿔치기 | 해시 결박, `stale` 판정 |
| 외부인이 워크플로를 시작함 | 트리거는 `main` 푸시와 수동 실행뿐, 소유자 확인 |
| PoC가 자격 증명·네트워크에 접근 | 네트워크 없음, 허용목록 환경, 읽기 전용 대상, 토큰 권한 없음 |
| 실행 결과물이 저장소를 오염 | scratch 폐기, 증거는 캡처 출력만, 기록 작업 분리와 재검증 |
| 약한 샌드박스에서 조용히 실행 | 통제를 실행마다 프로브, 실패 시 중단 |
| 재현 한 번으로 과신 | 3회 반복 + control, 최종 판정은 사람 |
