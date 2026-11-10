# 도구 사용 기록 — run-1

요청된 5개 도구를 어떻게 썼고 무엇이 나왔는지, 쓰지 못한 부분은 무엇인지 적는다. 도구 리포는 모두 읽기 전용으로 클론했고, 어느 쪽에도 아무것도 보내지 않았다. 사용한 커밋은 `tool-logs/tool-provenance.tsv`.

| 도구 | 성격 | 이번에 한 일 | 하지 못한 일 |
|---|---|---|---|
| `google/osv-scanner` | 의존성 취약점 스캐너 | 소스에서 빌드(v2.7.1)해 실행 | — |
| `NVIDIA/SkillSpector` | 에이전트 스킬 스캐너 | 정적 모드(`--no-llm`)로 실행 | LLM 의미 분석 단계 (API 키 없음) |
| `alibaba/open-code-review` | AI 코드리뷰 CLI | 소스에서 빌드. 파일 선정과 룰 해석만 실행 | `ocr scan` 본 리뷰 (LLM 설정 없음) |
| `cloudflare/security-audit-skill` | 6단계 감사 방법론 | 절차를 따라 수행, 번들 validator 2종으로 산출물 검증 | 독립 검증자·비평가 에이전트 (`REPORT.md` §1) |
| `anthropics/oss-scanner` | Anthropic이 운영하는 호스팅 스캔 서비스 | 등록 번들을 작성하고 도구의 `validate.py`로 검증 | **스캔 자체**. 등록은 그쪽 리포에 PR을 내야 한다 |

## osv-scanner

```bash
osv-scanner scan source -r --format json .
```

```bash
osv-scanner scan source --no-resolve --all-packages --format json -L requirements.txt:baselines/requirements_codeevolve.txt -L requirements.txt:baselines/requirements_openevolve_shinkaevolve.txt
```

- 첫 실행에서 `baselines/requirements_openevolve_shinkaevolve.txt`의 전이 의존성 해석이 실패했다(`aiohttp: "==3.14.5,<3.14.0,>=3.9.1"` 충돌). 누락을 막으려고 `--no-resolve`로 고정 핀을 직접 다시 검사했다.
- 실제 설치되는 두 파일의 결과: `requirements_codeevolve.txt` 20개 패키지 중 취약 0개. `requirements_openevolve_shinkaevolve.txt` 71개 패키지 중 취약 1개 — **`pillow==11.3.0`, 권고 58개 그룹**(CVSS 9.0 이상 5개, 7.0~8.9 38개, 4.0~6.9 15개). 수정 버전은 12.1.1~13.0.0에 걸쳐 있다.
- 재귀 스캔의 나머지 적중(`torch`, `scipy`, `pillow 9.5.0`, `transformers`, `anyio`, `certifi`, `idna`)은 전부 `baselines/openevolve/examples/*/requirements.txt`의 하한 지정에서 나온 것이고, `setup_baselines.sh`는 이 파일들을 설치하지 않는다.
- 분류: Pillow 핀은 **하드닝 메모**다. 헌터가 범위 내 코드에서 `PIL`/`Image.open` 사용처를 추적했고, 신뢰할 수 없는 이미지가 Pillow에 닿는 경로를 찾지 못했다.

기록: `tool-logs/osv-scanner/summary.json`(패키지별 권고 ID·심각도·수정 버전), `recursive-noresolve.md`, stderr 로그. 권고문 전문이 든 원본 JSON(4.3MB)은 커밋하지 않았다. 위 명령으로 다시 만들 수 있다.

## SkillSpector

```bash
skillspector scan baselines/ShinkaEvolve/skills --recursive --no-llm --format json
```

대상은 ShinkaEvolve의 에이전트 스킬 4개와 에이전트 지시 파일 2개(`baselines/openevolve/CLAUDE.md`, `baselines/CodeEvolve/AGENTS.md`).

| 대상 | 점수 | 지적 |
|---|---|---|
| `shinka-convert` | 14/100 LOW | `LP3`(SKILL.md:1), `EA2`(SKILL.md:59) |
| `shinka-inspect` | 7/100 LOW | `LP3`(SKILL.md:1) |
| `shinka-run` | 0/100 LOW | 없음 |
| `shinka-setup` | 14/100 LOW | `LP3`(SKILL.md:1), `EA2`(SKILL.md:25) |
| `CLAUDE.md`, `AGENTS.md` | 0/100 | 없음 |

헌터의 분류: `EA2`(과도한 에이전시) 2건은 **오탐** — 지적된 줄은 "동의 없이 하지 말라"는 요구 문장이다. `LP3`(도구 권한 미선언) 3건은 **하드닝 메모**. 정적 스캐너가 잡지 못한 것을 헌터가 소스에서 찾았다: `shinka-inspect`가 생성 프로그램 텍스트를 고정 길이 코드 펜스에 넣는 문제(`shinka-inspect/context-bundle-fence-breakout`).

기록: `tool-logs/skillspector/`.

## open-code-review

```bash
ocr scan --preview --format json --audience agent
```

```bash
ocr delegate rule <핵심 파일 12개>
```

- 미리보기: 1,144개 파일 중 681개가 리뷰 대상, 463개 제외(확장자 미지원 247, 기본 경로 제외 180, 바이너리 29, 크기 초과 7).
- LLM 설정이 없어 OCR이 직접 리뷰하는 `ocr scan`은 돌리지 않았다. 대신 Delegation 모드로 OCR이 해석한 룰을 뽑아 헌터 7명의 필수 읽기 자료로 넣었다. OCR 문서가 설명하는 "호스트 에이전트가 리뷰를 수행"하는 방식이다.
- 따라서 OCR 고유의 리뷰 코멘트 산출물은 없다. OCR이 기여한 것은 파일 선정과 룰이다.

기록: `tool-logs/open-code-review/delegate-rules.txt`, `scan-preview-summary.json`.

## security-audit-skill

전체 흐름의 뼈대로 썼다.

| 단계 | 한 일 | 산출물 |
|---|---|---|
| 1 정찰 | 읽기 전용 에이전트 4개로 구조·주체·진입점·실행 환경 매핑 | `architecture.md`, `coverage-ledger.json` |
| 2 헌팅 | 원장의 13개 유닛을 헌터 7명에게 배정, 1회 웨이브 | `hunters/*.json` (후보 23건) |
| 3 검증 | 조정자가 직접 재검토 (편차) | 유지 21, 기각 2 |
| 4 구조화 출력 | 스킬 스키마에 맞춰 기록 | `findings.json` |
| 5 기록 검증 | `quick` 프로파일에서는 3단계와 합쳐짐 | — |
| 6 보고 | 최종 기록에서 산문 도출 | `REPORT.md`, `NEEDS-VALIDATION.md`, `FINDINGS-DETAIL.md` |

```bash
node <skill>/validate-coverage-ledger.cjs coverage-ledger.json
```

```bash
node <skill>/validate-findings.cjs findings.json
```

최종 결과: `PASS: 19 coverage units valid`, `PASS: 23 findings valid`. validator 통과는 형식과 원장 일관성을 뜻할 뿐이고, 내용의 옳음을 보증하지 않는다.

## oss-scanner

이 리포는 스캐너 프로그램이 아니라 Anthropic이 운영하는 서비스의 **등록 창구**다. 스캔을 받으려면 `anthropics/oss-scanner`에 `projects/<name>/project.yaml`을 추가하는 PR을 내야 하고, 스캐너 본체는 리포에 들어 있지 않다. 그래서 로컬에서 스캔을 돌릴 수 없었고, 등록 PR도 내지 않았다.

한 일:

- 템플릿을 바탕으로 `.oss-scanner/`에 `Dockerfile`, `threat_model.md`, `report_guidelines.md`, `patch_guidelines.md`를 작성했다.
- 등록 파일 초안은 `.oss-scanner/enrollment/project.yaml`에 두었다. **제출하지 않은 초안**이다. `primary_contact`는 자리표시자다(그쪽 리포에서 공개되는 주소라 실제 주소를 넣지 않았다).
- 도구의 `tools/validate.py`를 임시 복사본에서 돌려 초안이 등록 규칙을 통과함을 확인했다: `ok: 1 project(s)`.
- `tools/check`(Docker로 빌드해 보는 점검)는 이 환경에 Docker 데몬이 없어 실행하지 못했다. `Dockerfile`의 두 `pip install` 단계만 Python 3.13 가상환경에서 따로 실행해 성공을 확인했다. **이미지 빌드 전체는 검증되지 않았다.**

`.oss-scanner/Dockerfile`은 승인 게이트 파이프라인의 샌드박스 이미지로도 쓴다. `threat_model.md`의 심각도 기준은 이번 조사에서 후보를 고를 때 쓴 기준과 같다.
