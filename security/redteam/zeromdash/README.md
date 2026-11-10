# ZeroMDASH로 직접 돌리기

**이 설정은 실행해 보지 않았다.** ZeroMDASH의 README와 데모 설정(커밋 `9cb2752`)을 읽고 쓴 것이다. 설치한 버전의 옵션과 맞는지 먼저 확인한다.

필요한 것: Python 3.10 이상, 코딩 에이전트 런타임(여기서는 Claude Code)과 그 자격 증명. 조사자·비평가를 여러 개 띄우므로 비용이 크다. `agent-config.yaml`의 `top_K`와 `max_concurrency`를 작게 잡아 두었다.

## 순서

1. 공격 표면 분석까지만 돌려 계획을 본다.

   ```bash
   zeromdash --target . --workspace-root /tmp/zeromdash-swarmevolve --agent-config security/redteam/zeromdash/agent-config.yaml --preset-attack-surface security/redteam/zeromdash/preset-attack-surface.md --till-node plan
   ```

2. `/tmp/zeromdash-swarmevolve/workspace_for_*/log/state/plan_by_*.json`을 읽고 조사할 가치가 있는지 판단한다.

3. 조사·비평·체인 단계를 이어서 돌린다.

   ```bash
   zeromdash --start-from-subtask /tmp/zeromdash-swarmevolve/workspace_for_<target>
   ```

워크스페이스는 리포 **밖**에 둔다(`--workspace-root`). ZeroMDASH는 대상 소스 전체를 워크스페이스에 복사한다.

## 결과를 이 리포의 흐름에 태우기

| ZeroMDASH 산출물 | 옮길 곳 |
|---|---|
| `main/attack_surface/domain_invariant_registry.json` | `security/redteam/registry/domain-invariant-registry.json`과 병합 |
| `log/primitive_res/*.json` | `security/redteam/registry/capabilities.json`의 노드 (`status`를 `confirmed_primitive`로) |
| `log/subtask_res/*.json`의 standalone finding | `security/candidates/candidates.json` |
| `log/chain_res/*.json` | 체인 조사 기록. `chains.py` 결과와 대조 |

ZeroMDASH가 "confirmed"라고 한 것도 여기서는 `needs_validation`으로 들어온다. 이 리포에서 확정은 승인된 샌드박스 관찰이 있어야 한다.

## 하지 말 것

- `zeromdash-repro`를 이 대상에 쓰지 않는다. PoC를 만들고 실행하는 도구다. 이 리포의 PoC 실행은 `security/DESIGN.md`의 승인 게이트를 거친다.
- 대상 히스토리 조회(`search_target_history`)와 유사 소프트웨어 조회는 외부 네트워크를 쓴다. 원치 않으면 `--disable-target-history`를 붙인다.
- 워크스페이스에는 대상 소스 사본과 에이전트 로그가 들어 있다. 통째로 커밋하지 않는다.
