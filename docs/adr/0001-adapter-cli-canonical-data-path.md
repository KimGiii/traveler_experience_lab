# ADR 0001 — 어댑터 CLI를 유일한 정규화 데이터 경로로 고정

- 상태: 채택(Accepted)
- 날짜: 2026-07-02
- 관련: [`../schema/contract.md`](../schema/contract.md), [`../schema/field_notes.md`](../schema/field_notes.md)

## 맥락
플러그인은 Codex-first, Claude-compatible **듀얼 런타임**이며 런타임 무관 공용 코어(`core/`)를 공유한다.
MCP 접근 방식으로 두 경로가 존재하게 됐다:
1. **어댑터 CLI** (`python3 -m core.cli`) — JSON-RPC 호출을 감싸 응답을 `ScenarioFixture`로 정규화.
2. **번들 MCP 서버** (`.mcp.json` 의 `myrealtrip`) — Codex가 MCP 툴을 네이티브로 직접 호출.

검증(2026-07-01)에서 응답 구조가 도메인마다 비대칭임이 확인됐다: `searchStays`는 `structuredContent`,
`searchTnas`는 `widget`+`copy_text`(정형 필드 없음), detail 계열은 `content[0].text` JSON. 실패도 2종
(`isError` 비즈니스 오류 / `-32602` 검증 오류)이다.

## 결정
**모든 ScenarioFixture 생성은 어댑터 CLI(`core.cli` → `core.mcp.adapters`)를 경유한다.**
명령 본문(`commands/`)과 이후 오케스트레이션은 MCP 툴을 직접 호출하지 않는다.

### `.mcp.json` 사용 금지선 (명시)
- ✅ **허용**: 사람이 하는 **네이티브 탐색·디버깅**(툴 목록/스키마 즉석 확인, 응답 눈으로 보기).
- 🚫 **금지**: `.mcp.json` 의 `myrealtrip` 툴을 **ScenarioFixture 데이터 경로로 직접 호출**하는 것.
  즉 정규화 대상 데이터를 어댑터를 우회해 가져오지 않는다.

## 근거
1. **비대칭 흡수**: 3가지 응답 구조를 `ProductCandidate` 단일 형태로 결정적으로 통일. 직접 호출은 매 호출·런타임마다 파싱이 흔들린다.
2. **파생 필드 재현성**: gid=URL 말미 추출, `copy_text` 순서 매핑, `isSoldOut→available` 등 규칙 기반 로직은 코드로 고정해야 재현된다.
3. **실패 판정 일원화**: `unwrap` 한 곳에서 `isError` 2종을 판정 → CLI·probe·normalizer가 동일 기준. (P2-2 회귀 방지)
4. **듀얼 전제 유지**: 어댑터 경유 시 두 런타임이 바이트 동일한 ScenarioFixture를 얻는다. 직접 호출은 런타임별로 결과가 갈려 "공용 코어"가 무너진다.
5. **오프라인 검증**: `fixtures/` 로 네트워크 없이 정규화·회귀 검증 가능(`tests/` 골든).
6. **보안 집행점**: "전송 데이터 명시 / PII 차단"을 CLI 단일 경계에서 강제.

## 결과 (집행 방식)
- **CLI 표면 분리** — 정규화 데이터 경로와 디버깅 표면을 명령 단위로 나눈다:
  - 정론(데이터 경로): `core.cli fetch <tool>`(정규화된 candidates 반환), `core.cli probe`(fixtures 생성).
  - 디버깅 전용(raw): `core.cli call`(출력에 `_debug` 표식), `core.cli list-tools[-raw]`. 이들로 ScenarioFixture를 만들지 않는다.
- `commands/*.md`, `skills/**/SKILL.md`, `AGENTS.md`, `README.md` 는 시나리오 데이터로 **`fetch`만** 안내한다.
- `.mcp.json` 은 유지하되 위 금지선을 따른다(직호출은 사람 디버깅 한정).
- 계약·드리프트·에러·**CLI 표면** 골든은 [`../schema/contract.md`](../schema/contract.md) 와 `tests/test_contract_golden.py` 로 강제된다.

## 재검토 트리거
- MCP가 모든 도구에 정형 `structuredContent`를 제공하게 되어 정규화 가치가 줄어들 때.
- 런타임이 서버측 정규화를 제공하게 될 때.
