# Traveler Experience Lab — Codex 작업공간 가이드

마이리얼트립 PE용 플러그인. **런타임 무관 공용 코어**(`core/`)를 Claude Code와 Codex가 얇게 공유하는 **듀얼 구조**다.

Codex 플러그인 설치/노출 진입점은 `.codex-plugin/plugin.json` 과 `skills/traveler-experience-lab/SKILL.md` 이다. 이 파일은 이 저장소를 작업공간으로 열었을 때의 운영 가이드이며, 명령 본문의 단일 출처는 `commands/`다.

## 무엇을 하는가
여행자 경험 문제를 **실시간 MRT 상품 인벤토리(MCP)** + **비식별 VoC**로 근거화해 문제 정의→시나리오→구현 브리프까지 얇게 정리한다. 범용 LLM이 못 하는 두 해자(실시간 인벤토리, 실제 VoC)에만 집중한다.

## 명령 (2개 wedge)
| 명령 | 본문(단일 출처) | 요약 |
|---|---|---|
| `/mrt scenario` | [`commands/scenario.md`](commands/scenario.md) | 실제 상품 근거 여행자 시나리오 + 실험/QA 초안 |
| `/mrt diagnose` | [`commands/diagnose.md`](commands/diagnose.md) | 비식별 VoC → 여정/마찰 구조화 → scenario 핸드오프 |

Codex에서 위 명령을 실행할 때는 해당 `commands/*.md`의 지시를 그대로 따른다.

## 데이터 접근 — 어댑터 스크립트 경유 (유일 경로)
MCP를 직접 호출하지 말고 항상 공용 어댑터 CLI를 경유한다(런타임 무관, stdlib 전용). **정규화 데이터 경로와 디버깅 표면을 구분한다:**

```bash
# 오케스트레이션 (권장 — 브리프 → plan → fetch → ScenarioFixture)
python3 -m core.cli scenario --destination <목적지> --period <YYYY-MM-DD~YYYY-MM-DD> [--destination-iata <IATA>]

# 정규화 데이터 경로 (개별 fetch/체이닝)
python3 -m core.cli fetch <tool> --args '{...}'     # → 정규화된 candidates
python3 -m core.cli probe --samples <samples.json>  # 도메인 샘플 스윕 → fixtures/

# 디버깅 전용 (raw — ScenarioFixture 생성에 사용 금지)
python3 -m core.cli list-tools            # 도구 목록
python3 -m core.cli list-tools-raw        # inputSchema
python3 -m core.cli call <tool> --args '{...}'   # raw result (_debug 표식)
```

- 엔드포인트: `https://mcp-servers.myrealtrip.com/mcp` (인증 없음, JSON-RPC/HTTP POST).
- 응답 정규화 목표: `core/schema/scenario_fixture.py` 의 `ScenarioFixture`.

### `.mcp.json` 역할 구분 (금지선 — [ADR 0001](docs/adr/0001-adapter-cli-canonical-data-path.md))
- `.mcp.json` 의 `myrealtrip` MCP 서버는 **사람의 네이티브 탐색·디버깅 전용**이다.
- 🚫 **ScenarioFixture 데이터 경로로 `myrealtrip` 툴을 직접 호출하지 말 것.** 정규화 대상 데이터는 **반드시 `core.cli` 어댑터**를 경유한다. (이유: 응답 비대칭 흡수·파생필드 재현성·실패판정 일원화·듀얼 런타임 동일성 — ADR 0001 참고.)

## 보안 원칙 (엄수)
- 고객명·전화·이메일·예약번호·결제정보 **입력 금지**.
- VoC는 **비식별 요약**만. 원문·PII 반입 금지.
- 외부 MCP 호출 전 **전송 데이터 명시**.
- 내부 정책/코드는 로컬 컨텍스트에서만 사용, 외부 원문 전송 금지.

## 구조
```
core/                 # 런타임 무관 공용 코어
  mcp/client.py       # JSON-RPC/HTTP MCP 클라이언트 (stdlib)
  mcp/endpoints.py    # 엔드포인트 + 도구명 상수
  mcp/adapters.py     # result → ProductCandidate 정규화 (검증 후 확정)
  schema/…            # ScenarioFixture 스키마 (초안)
  scenario/           # 오케스트레이션: plan → fetch → assemble (inputs/planning/assembly/orchestrator)
  cli.py              # 어댑터 CLI (양 런타임 공용 진입점; scenario/fetch/probe/…)
commands/             # 명령 본문 (Claude Code + 공용 단일 출처)
skills/               # Codex skill 진입점
prompts/              # Codex 프롬프트 래퍼 (레거시/참고)
fixtures/             # 샘플 호출 산출물 (검증 근거)
docs/schema/          # 스키마 초안 + 필드 노트
```
