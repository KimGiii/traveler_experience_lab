# ProductCandidate / ScenarioFixture 계약

> 코드 강제: [`../../core/schema/scenario_fixture.py`](../../core/schema/scenario_fixture.py) (`validate_candidate`, `dedupe_candidates`, `__post_init__`)
> 골든 테스트: `tests/test_contract_golden.py` · 관련 결정: [`../adr/0001-adapter-cli-canonical-data-path.md`](../adr/0001-adapter-cli-canonical-data-path.md)

## ProductCandidate 필드 계약

| 필드 | 필수/Nullable | 규칙 |
|---|---|---|
| `domain` | **필수** | `("flights","stays","tnas")` 중 하나. 위반 시 `__post_init__`에서 `ValueError`. |
| `source` | **필수** | `SourceRef`(tool+arguments). 프로비넌스. `validate_candidate`가 강제. |
| `raw` | **필수** | 후보가 파생된 **소스**를 보존(파생·재합성 금지). 응답이 상품별 정형 객체를 줄 때(항공 `items[]`, 숙소 `stays[]`, detail 계열)는 **그 객체 전체**. 위젯/copy_text 응답(TNA search)처럼 상품별 객체가 없으면 후보가 나온 **원문 소스 조각**(copy_text 블록 + product_url). 전체 `tools/call` 응답의 무손실 지문은 `fetch`/`probe`/`scenario` 출력의 `_meta.raw_sha256` 또는 `_meta.responses[].raw_sha256`가 별도 보장. `validate_candidate`가 non-None 강제. |
| `title` | nullable | 없음 = "이 도구가 제공 안 함", "빈 값 확정" 아님. |
| `price` | nullable | `Price`(amount/currency/text/original_amount) 또는 None. |
| `rating` | nullable | 있으면 `0.0 ≤ rating ≤ 5.0`. |
| `review_count` | nullable | 정수. |
| `booking_url` | nullable | reservationUrl / product url / shareWebLink. |
| `identifier` | nullable | gid(stays/tnas) 또는 fare id(flights). |
| `available` | nullable | `isSoldOut`/`noRoomsAvailable`/`hasAvailableOptions` 파생. |
| `availability_note` | nullable | 예: "해당 날짜는 예약이 불가능합니다." |
| `free_cancellation` | nullable | stay room `isFreeCancellation` 파생. |
| `cancellation_note` | nullable | TNA `copy_text` 취소정책(있을 때만). |
| `edge_flags` | 필수(list) | `EDGE_CASES` 부분집합. 위반 시 `validate_candidate`가 `ValueError`. |

**Nullable 의미 규약**: `None` = *제공되지 않음*(unknown). *알려진 빈 값*이 아니다. 확정된 부재는 별도 플래그(예 `available=False`)로 표현한다.

## 정렬 기준
- 후보는 **MCP가 반환한 upstream 순서를 보존**한다(추천/관련도/`isCheapest` 랭킹이 의미를 가짐). 정규화기는 **재정렬하지 않는다**.

## De-duplication 기준
- 순서 보존, **첫 등장 우선**.
- 키 = `identifier` 존재 시 `(domain, "id", identifier)`, 아니면 `(domain, "fallback", title, booking_url)`.
- `normalize()` 반환 전에 `dedupe_candidates()` 적용.
- (별개) TNA 위젯 URL은 상품당 중복 등장 → `_dedupe()`로 순서 보존 제거 후 `copy_text` 순서와 1:1 매핑.

## 버전
- `SCHEMA_VERSION = "1"` (스키마 모양) · `NORMALIZER_VERSION = "1"` (매핑 로직). 로직/스키마 변경 시 각각 bump.

## 드리프트 감지 메타 (`fixtures/*/*.json` 의 `_meta`)
어댑터가 응답을 잘 흡수할수록 upstream 변화가 조용히 묻힐 수 있으므로, 각 fixture에 프로비넌스를 남긴다:

| 키 | 의미 |
|---|---|
| `raw_sha256` | `result` 정규 JSON(sort_keys)의 SHA-256. 재계산과 불일치 → **드리프트/변조**. |
| `source_type` | `structured` / `error` / `widget` / `content-json` / `unknown`. 응답이 데이터를 담는 방식. |
| `normalizer_version` | 이 fixture를 해석한 매핑 로직 버전. |
| `probed_at` | 수집 UTC 시각(해시 대상 아님). |

- 생성: `core.cli probe` 가 자동 기록 · 백필: `core.mcp.adapters.fingerprint(result)`.
- 검증: 골든 `DriftDetectionGolden.test_stored_hash_matches_recompute` 가 저장 해시 ↔ 재계산 일치를 강제.

## 에러 골든 (P2-2 회귀 방지)
성공만큼 중요한 실패 케이스를 fixture로 고정:
- `fixtures/flights/searchInternationalFlights.sample3.json` → **business** 오류(`isError`, `structuredContent.success=false`).
- `fixtures/stays/searchStays.sample2.json` → **validation** 오류(`-32602`, structuredContent 없음).
- 골든: `ErrorEnvelopeGolden` 가 두 케이스가 `McpToolError`(kind 일치)로 떨어지고 `ok=False`·`source_type="error"` 임을 강제.
