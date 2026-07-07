# Traveler Experience Lab

마이리얼트립 Product Engineer(PE)가 여행자 경험 문제를 **실시간 상품 인벤토리(MCP)** + **실제 VoC**로 근거화해, 문제 정의부터 구현 브리프까지 얇고 날카롭게 정리하도록 돕는 플러그인.

기획 배경·전략은 [`traveler_experience_lab_plan.md`](traveler_experience_lab_plan.md) 참조.

## 런타임 구조 (듀얼)
런타임 무관 **공용 코어**(`core/`)를 Claude Code와 Codex가 얇게 공유한다.

| 런타임 | 진입점 | 명령 |
|---|---|---|
| Claude Code | [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json) + [`commands/`](commands) | `/mrt scenario`, `/mrt diagnose` |
| Codex | [`.codex-plugin/plugin.json`](.codex-plugin/plugin.json) + [`skills/traveler-experience-lab/SKILL.md`](skills/traveler-experience-lab/SKILL.md) + [`.mcp.json`](.mcp.json) | 동일 (commands/ 단일 출처) |

## 어댑터 CLI (MCP 유일 경로)
```bash
# 오케스트레이션 (권장 — 브리프 → plan → fetch → ScenarioFixture 한 방)
python3 -m core.cli scenario --destination "오사카" --period "2026-09-10~2026-09-13" --persona "가족"

# 정규화 데이터 경로 (ScenarioFixture 재료 — 개별 fetch/체이닝)
python3 -m core.cli fetch searchTnas --args '{"query": "오사카 유니버설 스튜디오"}'   # → candidates
python3 -m core.cli probe --samples docs/schema/samples.json --out fixtures          # 샘플 스윕 → fixtures/

# 디버깅 전용 (raw — 시나리오 구성에 사용 금지)
python3 -m core.cli list-tools                         # tools/list (compact)
python3 -m core.cli list-tools-raw                     # inputSchema
python3 -m core.cli call searchTnas --args '{"query": "오사카"}'   # raw result
```
- 엔드포인트: `https://mcp-servers.myrealtrip.com/mcp` (인증 없음, JSON-RPC/HTTP POST)
- Python 3 표준 라이브러리만 사용 — 별도 설치 불필요.

> **역할 구분 (금지선 · [ADR 0001](docs/adr/0001-adapter-cli-canonical-data-path.md))**: [`.mcp.json`](.mcp.json) 의 `myrealtrip` MCP 서버는 **네이티브 탐색·디버깅 전용**이다. ScenarioFixture 생성에는 사용 금지 — 정규화 데이터 경로는 **`core.cli` 어댑터 단일 정론**이다.
> 계약·드리프트·에러 골든: [docs/schema/contract.md](docs/schema/contract.md), `tests/test_contract_golden.py`.

## 디렉토리
```
core/            런타임 무관 공용 코어 (MCP 클라이언트 / 스키마 / 시나리오 오케스트레이션 / CLI)
commands/        명령 본문 (단일 출처)
skills/          Codex skill 진입점
prompts/         Codex 프롬프트 래퍼(레거시/참고)
fixtures/        샘플 호출 산출물 (검증 근거 + 드리프트 _meta) + 공개 VoC 비식별 샘플(voc/)
docs/schema/     스키마 초안 + 필드 노트 + 계약(contract.md)
docs/voc/        VoC 0주차 게이트 판정 기록
docs/baseline/   baseline 측정 프로토콜 + 기록 시트
docs/pilot/      파일럿 스모크/실행 기록
docs/adr/        아키텍처 결정 기록 (ADR)
tests/           계약·에러·드리프트 골든 테스트 (stdlib unittest)
log-hooks/       대화 로그 저장 훅 (claude-code / codex)
```

## 보안 원칙
고객 PII(이름·전화·이메일·예약번호·결제정보) 입력 금지. VoC는 비식별 요약만 사용.
자세한 내용은 계획서 §6.
