# 보안 조사 보고서 — run-1

## 1. 실행 조건

| 항목 | 값 |
|---|---|
| 대상 | `Topabaem05/SwarmEvolve-cyber` @ `a944b3d` (작업 트리 변경 없음) |
| 범위 | `benchmarks/`, `baselines/` (`examples/`, `tests/`, `docs/` 제외) |
| 프로파일 | `quick` — **부분 커버리지**. 한 번의 조사로 대상을 다 봤다고 주장하지 않는다 |
| 실행 정책 | 소스 분석만. **대상 코드는 한 줄도 실행하지 않았다** |
| 이전 실행 | 없음 |
| 에이전트 | 정찰 4 + 헌터 7 = 11회 사용 (예산 26) |
| 상태 | `incomplete` — 아래 "절차상 편차" 참고 |

### 절차상 편차

이 조사는 `cloudflare/security-audit-skill`의 6단계 절차를 따랐고, 다음 지점에서 벗어났다.

1. **독립 검증자·커버리지 비평가 에이전트를 실행하지 않았다.** 헌터 단계 이후 에이전트를 더 쓰지 말라는 요청에 따라, 헌터가 아닌 조정자(parent)가 후보 23건을 직접 재검토했다. 후보마다 결정적인 소스 줄은 다시 읽었지만 인용된 모든 줄을 읽지는 않았고, 나머지는 기계적으로만 확인했다(파일 존재, 줄 번호 범위, trace 순서). 스킬이 요구하는 "후보당 새 검증자 1명"보다 약한 검증이다.
2. **대상 코드를 실행하지 않았다.** 그래서 어떤 후보도 `confirmed`가 될 수 없고, 전부 `needs_validation` 또는 `rejected`다. 실행은 소유자 승인 후 샌드박스에서 한다(`security/DESIGN.md`).
3. 헌터 프롬프트에 스킬 문서 블록을 그대로 붙이는 대신 파일 경로로 지정해 읽게 했다.

## 2. 보안 상태 요약

이 리포는 LLM이 생성한 프로그램을 운영자 계정으로 그대로 실행하는 연구용 도구 모음이다. 그 자체는 이 부류 소프트웨어의 설계이므로 후보로 세지 않았다. 후보는 그 위에서 **다른 주체나 자원이 피해를 보는 경우**만 추렸다.

- **ShinkaEvolve 뷰어**가 가장 무겁다. 인증 없이 모든 네트워크 인터페이스에 바인드하고, 요청 경로를 search root 안에 가두지 못한다. 포트에 닿을 수 있는 클라이언트가 운영자 파일을 읽을 수 있다는 후보가 소스상 완결돼 있다.
- **벤치마크 점수 무결성**은 평가받는 프로그램과 같은 채널·같은 파일에 의존한다. 프로그램이 자기 점수를 정할 수 있다는 후보 여러 건이 나왔다. 논문의 프레임워크 간 비교가 이 로그를 읽는다.
- **공유 `/tmp`가 import 경로에 올라가는 패턴**이 세 곳에 있다. 다중 사용자 호스트에서만 의미가 있다.
- 확정된 취약점은 **0건**이다.

## 3. 확정된 발견

없음.

## 4. 검증 필요 (NEEDS VALIDATION) — 21건

심각도는 부여하지 않았다. 확정된 취약점이 아니다. 전체 trace·근거·로컬 검증 계획은 `NEEDS-VALIDATION.md`, 기계 판독용은 `findings.json`.

"순위"는 검증을 먼저 할 순서이고 심각도가 아니다. 기준: 낮은 신뢰 주체가 기본 설정에서 닿을 수 있는가, 보호 대상이 무엇인가.

### ShinkaEvolve 뷰어 — `baselines/ShinkaEvolve/shinka/webui/`

| 순위 | fingerprint | 주장 | 핵심 위치 | 확정을 막는 사실 |
|---|---|---|---|---|
| 1 | `shinka-webui/plot-file-unrestricted-read` | `/plot_file/`이 search root(기본값: 실행한 디렉터리) 아래 어떤 파일이든 반환한다. 포함 여부를 문자열 접두사로만 비교해 `root_sibling` 같은 형제 디렉터리도 통과한다 | `visualization.py:987-1012` | 로컬 관찰 없음. 포트 도달 가능성 |
| 1 | `shinka-webui/db-path-traversal` | `db_path` 쿼리 값이 search root에 그대로 결합된다(10곳). 루트 밖의 Shinka sqlite DB와 `meta_*.txt`를 읽을 수 있다 | `visualization.py:428-430, 449` | 로컬 관찰 없음. 루트 밖에 해당 형식 파일이 있는지 |
| 1 | `shinka-webui/wildcard-bind-no-auth` | 모든 인터페이스에 바인드하고 인증이 없다. 바인드 주소를 고르는 옵션도 없다. 문서는 SSH 터널을 쓰라고 하지만 코드가 강제하지 않는다 | `visualization.py:1740` | 호스트 방화벽·네트워크 구성 |
| 2 | `shinka-webui/cors-wildcard-json-api` | 모든 JSON 응답에 `Access-Control-Allow-Origin: *`. 운영자 브라우저가 방문한 임의 사이트가 뷰어 API를 읽을 수 있다 | `visualization.py:1681` | 브라우저의 사설망 접근 정책 |
| 2 | `shinka-webui/dom-xss-llm-derived-fields` | 모델 응답에서 뽑은 `patch_name` 등이 이스케이프 없이 `innerHTML`에 들어간다 | `viz_tree.html:5688-5693` | 브라우저 관찰. CDN에서 받는 `marked` 버전 동작 |

### 벤치마크 채점 — `benchmarks/`

| 순위 | fingerprint | 주장 | 핵심 위치 | 확정을 막는 사실 |
|---|---|---|---|---|
| 1 | `benchmarks-evaluation/inband-metrics-marker-forgery` | 프로그램이 `@@METRICS@@` 줄을 직접 출력하고 종료 코드 0으로 끝내면 그 점수가 기록된다. 채점기는 마지막 마커 줄을 믿고 종료 코드를 보지 않는다 | `evaluation.py:50-52`, `run_evaluator.py:12-16` | 로컬 관찰 없음 |
| 1 | `benchmarks-evaluation/eval-log-writable-by-evaluated-program` | 점수의 원본인 `EVAL_LOG` 경로가 환경 변수로 프로그램에 전달되고, 프로그램이 그 파일에 직접 쓸 수 있다 | `evaluation.py:46, 72-75`, `run_baseline.sh:55` | 로컬 관찰 없음. 로그를 읽는 집계 스크립트가 리포에 없음 |
| 2 | `benchmarks-scientific-cases/reference-answers-readable-by-program` | 주석은 자식 프로세스가 "정답은 절대 받지 않는다"고 하지만, 정답 파일은 같은 계정으로 읽을 수 있다 | `scientific_cases.py:2-5, 19-29` | 로컬 관찰 없음 |
| 2 | `benchmarks-evaluation/time-limit-process-escape` | 프로세스 그룹 kill은 타임아웃일 때만 실행된다. 세션을 벗어난 자손은 60초 제한 뒤에도 남는다 | `evaluation.py:41, 55-56` | 로컬 관찰 없음. 외부 격리 유무 |
| 2 | `circle-packing-26-evaluator/results-pickle-load` | 평가기가 프로그램의 자식이 쓴 결과 파일을 `pickle.load`한다. 프로그램과 채점기를 프로세스로 나눈 유일한 평가기에서 그 분리가 사라진다 | `problems/circle_packing_26/evaluator.py:166-168` | 로컬 관찰 없음 |
| 3 | `circle-packing-26-evaluator/shared-tempdir-on-module-search-path` | 래퍼 스크립트를 공유 `/tmp`에 만들고 스크립트로 실행해 `/tmp`가 `sys.path` 맨 앞에 온다 | `problems/circle_packing_26/evaluator.py:95, 148` | 같은 호스트의 다른 로컬 사용자 존재 여부 |

### OpenEvolve — `baselines/openevolve/`

| 순위 | fingerprint | 주장 | 핵심 위치 | 확정을 막는 사실 |
|---|---|---|---|---|
| 2 | `openevolve-visualizer/sidebar-innerhtml-unescaped-llm-text` | 프롬프트·LLM 응답·artifact가 이스케이프 없이 `innerHTML`에 들어간다. 같은 파일의 코드 탭은 이스케이프한다 | `scripts/static/js/sidebar.js:421` | 브라우저 관찰 |
| 2 | `openevolve-visualizer/static-export-inline-script-json-breakout` | 정적 내보내기가 실행 데이터를 인라인 `<script>`에 넣는다. 생성 텍스트의 `</script>`가 스크립트를 끊을 수 있다 | `scripts/visualizer.py:158-160` | 설치된 Flask 3.1.3의 직렬화 동작 관찰 |
| 2 | `openevolve-visualizer/manual-answer-unauthenticated-reply-injection` | manual 모드 엔드포인트가 인증 없이 작업 목록을 주고 답을 받는다. 그 답이 LLM 응답이 되어 실행된다 | `scripts/manual.py:136-142, 159-177` | manual 모드는 기본 꺼짐. 다른 로컬 사용자·DNS rebinding 가능 여부 |
| 3 | `openevolve-evaluator/shared-tmp-program-import-path` | 후보 프로그램을 공유 `/tmp`에 쓰고, 평가기가 그 디렉터리를 `sys.path` 맨 앞에 넣는다 | `openevolve/evaluator.py:259` | 다른 로컬 사용자 존재 여부 |
| 3 | `openevolve-api/shared-tempdir-module-path` | 라이브러리 API가 평가기 모듈을 공유 임시 디렉터리에 쓰고 import 경로에 넣는다. **이 리포의 글루는 이 API를 쓰지 않는다** | `openevolve/api.py:359-362` | 위와 같음 |

### 재개 시 역직렬화·설정·글루

| 순위 | fingerprint | 주장 | 핵심 위치 | 확정을 막는 사실 |
|---|---|---|---|---|
| 2 | `baselines-glue/vllm-localhost-endpoint-impersonation` | `run_baseline.sh`가 잡았다 놓은 포트에서 먼저 응답하는 프로세스를 모델 서버로 받아들인다. 그 프로세스가 생성 프로그램 전부를 정한다 | `run_baseline.sh:29, 36` | 공유 호스트 여부. 타이밍 |
| 3 | `shinka-bandit-state/pickle-load-on-resume` | 재개 시 `bandit_state.pkl`을 `pickle.load`한다. **이 리포의 글루 설정(`llm_dynamic_selection: None`)에서는 도달하지 않는다** | `shinka/llm/prioritization.py:218-220` | 남에게서 받은 결과 디렉터리를 재개하는 사용 방식 |
| 3 | `codeevolve-ckpt/pickle-load-on-resume` | 재개 시 체크포인트를 `pickle.load`한다. **이 리포의 글루(`--load_ckpt 0`)에서는 도달하지 않는다** | `CodeEvolve/src/codeevolve/utils/ckpt.py:114-115` | 위와 같음 |
| 3 | `codeevolve/config-template-verify-ssl-false` | 배포된 설정 템플릿이 API 키를 싣는 클라이언트의 TLS 검증을 끈다. **이 리포의 실행 경로는 로컬 http라 해당 없음** | `CodeEvolve/configs/templates/config_*.yaml:40-45` | 템플릿을 원격 엔드포인트에 쓰는지 |
| 3 | `shinka-inspect/context-bundle-fence-breakout` | 스킬이 만드는 컨텍스트 파일에서 생성 프로그램 텍스트가 코드 펜스를 벗어날 수 있다. 조정자가 줄 단위로 재추적하지 않은 후보 | `skills/shinka-inspect/scripts/inspect_best_programs.py` | 에이전트 런타임 동작 |

### 승인 즉시 실행 가능한 후보

하네스 초안이 있는 후보는 2건이다. 둘 다 소스 분석으로 작성했고 **아직 한 번도 실행하지 않았다.**

- `benchmarks-evaluation/inband-metrics-marker-forgery`
- `shinka-webui/plot-file-unrestricted-read`

나머지 19건은 `NEEDS-VALIDATION.md`의 로컬 검증 계획을 하네스로 옮긴 뒤 승인한다.

## 5. 기각한 후보 — 2건

발견이 아니다. 다음 조사에서 같은 주장을 반복하지 않도록 `findings.json`에 남긴다.

- `shinka-webui/meta-pdf-html-injection` — 모델이 쓴 meta 텍스트가 wkhtmltopdf로 가지만, PDF는 요청자에게 돌아가고 모델은 받지 못한다. 요청자는 이미 위의 파일 읽기 후보로 더 많은 것을 읽을 수 있다. 경계를 넘어 얻는 것이 없어 하드닝 메모로 내렸다.
- `openevolve-ci/claude-workflow-no-actor-gate` — 이 리포에는 루트 `.github/`가 없어 벤더링된 워크플로가 실행되지 않는다. 활성화된 리포에서도 결정적 통제는 리포 밖 서드파티 액션 안에 있다.

## 6. 하드닝 메모와 좋은 패턴

헌터들이 남긴 메모 63건은 `hardening-notes.json`에 있다. 그중 바로 손댈 만한 것:

- `baselines/requirements_openevolve_shinkaevolve.txt`의 `pillow==11.3.0`은 OSV 권고 58개 그룹에 걸린다. 다만 범위 내 코드 어디에서도 신뢰할 수 없는 이미지를 Pillow로 열지 않아 현재는 도달 경로가 없다. 논문 환경을 다시 검증할 수 있을 때 핀을 올린다.
- 두 requirements 파일은 `==`로 고정돼 있지만 해시가 없다. `--require-hashes`를 고려한다.
- OpenEvolve 뷰어는 `--debug`와 비-loopback `--host` 조합을 막지 않는다. 그 조합을 거부하게 한다.
- OpenEvolve의 `claude -p` 백엔드는 Codex 백엔드와 달리 도구 제한 없이 실행된다(다음 조사 유닛으로 보류).
- 루트 `.gitignore`가 `baselines/.env`, `benchmarks/.env`를 무시하지 않는다.
- `benchmarks/problems/circle_packing_26/evaluator.py`는 `program_path`를 생성 소스에 f-string으로 끼워 넣는다. 지금은 LLM이 경로를 정하지 못해 후보가 아니지만 `repr()`로 넣는 편이 안전하다.

소스에서 확인한 좋은 패턴: YAML은 전부 `safe_load`. SQL은 전부 바인드 파라미터. `scientific_cases.py`는 프로그램 출력을 `np.load(allow_pickle=False)`로 읽는다. ShinkaEvolve `headless.py`는 `shlex.join`으로 인용한다. ShinkaEvolve의 `claude.yml`은 작성자 권한을 확인하고 액션을 SHA로 고정한다. 모델 출력이 프레임워크 쪽 파일 경로·명령·import 대상에 닿는 경로는 세 프레임워크 모두에서 찾지 못했다.

조정자가 추가로 확인한 것: 헌터가 "출처 미확인"으로 적은 `httpx2`/`httpcore2` 핀은 고정된 `openai==3.35.1`의 정식 의존성이다(설치 메타데이터의 `Requires-Dist: httpx2`).

## 7. 커버리지

`coverage-ledger.json` 19개 유닛 기준.

| 상태 | 수 | 뜻 |
|---|---|---|
| `candidate` | 12 | 조사했고 후보가 나옴 |
| `covered` | 1 | 조사했고 후보 없음 (모델 출력 → 프레임워크 쪽 sink) |
| `deferred` | 6 | **조사하지 않음** |
| `blocked` | 0 | |

보류된 6개 유닛 — 이번 조사에서 보지 않은 영역:

1. ShinkaEvolve의 import 시점 `.env` 자동 로딩(`<cwd>/.env`, `override=True`) — 헌터 2명이 독립적으로 미조사 표면으로 보고
2. CodeEvolve 코어 (CLI, 진화 루프, island 프로세스, LM 클라이언트)
3. OpenEvolve 코어 (controller, 병렬 워커, 설정 로딩, artifact 저장)
4. OpenEvolve CLI 에이전트 백엔드의 도구 권한
5. ShinkaEvolve 코어 중 웹 UI 밖 (DB, 임베딩, 가격 카탈로그 캐시, 요약기, CLI)
6. `benchmarks/calibration/` 스크립트

최종 커버리지 비평가는 실행하지 않았으므로 **깨끗한 커버리지라고 주장하지 않는다.** 스킬 저자들의 경험으로는 한 번의 실행이 반복 실행 전체가 찾는 것의 절반 정도를 찾는다. 다음 실행은 이 원장의 `deferred` 유닛부터 시작하면 된다.
