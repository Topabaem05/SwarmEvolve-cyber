# security/

이 리포에 대한 보안 조사 기록과, 후보를 **소유자 승인 후에만** 샌드박스에서 PoC·재현 검증하는 파이프라인.

> **현재 상태 (run-1, 대상 커밋 `a944b3d`)** — 확정 0건, 검증 필요 21건, 기각 2건. 대상 코드는 실행하지 않았다. 아래 후보는 소스 분석으로 만든 **미검증 후보**이고 확정된 취약점이 아니다.

## 어디에 무엇이 있나

| 경로 | 내용 |
|---|---|
| `audit/run-1/REPORT.md` | 조사 보고서. 여기부터 읽는다 |
| `audit/run-1/NEEDS-VALIDATION.md` | 후보 21건의 trace, 근거, 막힌 사실, 로컬 검증 계획 |
| `audit/run-1/TOOLS.md` | 도구 5종을 어떻게 썼고 무엇이 나왔는지 |
| `audit/run-1/findings.json` | 최종 기록 (기계 판독용, 스킬 스키마) |
| `audit/run-1/coverage-ledger.json` | 무엇을 조사했고 무엇을 보류했는지 |
| `audit/run-1/hunters/` | 헌터 7명의 원본 결과 |
| `audit/run-1/tool-logs/` | 스캐너 출력 |
| `DESIGN.md` | 승인 게이트 파이프라인 설계 |
| `candidates/candidates.json` | 파이프라인이 읽는 후보 목록 |
| `approvals/approvals.json` | 승인 원장. 지금은 비어 있다 |
| `pipeline/verify.py` | 러너 |
| `pipeline/poc/<slug>/` | PoC 하네스 |
| `evidence/` | 검증 증거가 쌓이는 곳 |
| `../.oss-scanner/` | 샌드박스 이미지 레시피, 위협 모델 |
| `../.github/workflows/security-poc-verify.yml` | 승인 커밋에 반응하는 워크플로 |

## 후보를 검증하려면

1. 후보 상태를 본다.

   ```bash
   python3 security/pipeline/verify.py list
   ```

   `not_approved`는 하네스가 있고 승인만 남은 후보, `harness_missing`은 하네스부터 써야 하는 후보다.

2. 하네스를 **읽는다.** 승인은 그 파일들의 정확한 내용에 결박된다. 예: `security/pipeline/poc/shinka-webui_plot-file-unrestricted-read/poc.py`

3. 승인을 기록한다.

   ```bash
   python3 security/pipeline/verify.py approve shinka-webui/plot-file-unrestricted-read --by <GitHub 로그인>
   ```

4. `main`에 커밋·푸시하면 워크플로가 네트워크 없는 컨테이너에서 하네스를 실행하고 증거를 `security-evidence` 브랜치에 남긴다.

   ```bash
   git add security/approvals/approvals.json
   ```

   ```bash
   git commit -m "security: approve PoC for shinka-webui/plot-file-unrestricted-read"
   ```

   ```bash
   git push origin main
   ```

   로컬에서 바로 돌릴 수도 있다.

   ```bash
   python3 security/pipeline/verify.py run --all-approved
   ```

5. `evidence/<slug>/<시각>/result.json`의 판정을 읽는다. `reproduced`면 증거를 검토해 `findings.json`의 판정을 올릴지 결정한다. 그 결정은 자동화돼 있지 않다.

승인 없이 `run`을 실행하면 아무것도 실행되지 않고 `blocked`로 끝난다.

## 지금 실행 가능한 것과 아닌 것

| 항목 | 상태 |
|---|---|
| 러너의 승인 게이트·판정 로직 | 단위 테스트 21개 통과 |
| unshare 샌드박스 백엔드 | 자체 점검 통과 (네트워크 차단, 최소 환경, 읽기 전용 대상, scratch 쓰기) |
| docker 샌드박스 백엔드, `.oss-scanner/Dockerfile` | **미검증.** 작성한 환경에 Docker 데몬이 없었다. 두 `pip install` 단계만 따로 확인 |
| GitHub Actions 워크플로 | **미실행.** YAML 문법만 확인. `main`에 병합돼야 동작한다 |
| 하네스 2건 | **초안, 미실행.** 첫 실행은 승인 후 |
| 나머지 후보 19건 | 하네스 없음. `NEEDS-VALIDATION.md`의 계획을 옮겨 써야 한다 |

```bash
python3 security/pipeline/verify.py selftest
```

```bash
python3 -m unittest discover -s security/pipeline/tests
```

## 주의

- 이 리포는 공개 포크다. 여기 적힌 후보는 누구나 볼 수 있다. 대부분 벤더링된 베이스라인(OpenEvolve, ShinkaEvolve, CodeEvolve)의 코드에 관한 것이고, 해당 프로젝트 관리자에게 알린 적은 없다.
- 벤더링된 커밋은 `baselines/setup_baselines.sh`에 적혀 있다. 업스트림 최신 버전에서 이미 고쳐졌는지는 확인하지 않았다.
