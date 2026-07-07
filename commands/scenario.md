---
description: 실시간 MRT 상품 인벤토리로 근거화한 여행자 시나리오 + 실험/QA 초안을 생성한다
argument-hint: "[목적지] [기간] [예산] [동행자] [목적/페르소나]"
---

# /mrt scenario

마이리얼트립 PE가 여행자 경험 문제를 **실제 상품 후보**로 근거화해 시나리오·엣지케이스·실험/QA 초안까지 얇게 정리하도록 돕는다.

## 입력
`$ARGUMENTS` 에서 다음을 파악한다(누락 시 사용자에게 되묻는다): 목적지, 여행 기간, 예산, 동행자, 목적/페르소나.

## 데이터 근거 (필수)
LLM 추측이 아니라 **실시간 MRT MCP**를 통해 실제 상품을 가져온다. **정규화 데이터 경로는 `core.cli`(→ `core.mcp.adapters`) 단일 정론**이다([ADR 0001](../docs/adr/0001-adapter-cli-canonical-data-path.md)).

### 권장: 오케스트레이션 한 방 (`core.cli scenario`)
입력 브리프를 넘기면 계획(plan) → 정규화 fetch → `ScenarioFixture` 조립까지 한 번에 수행하고, 실행/스킵/오류 트레이스를 함께 돌려준다. 아래 출력 5개 섹션(§출력)은 이 fixture를 근거로 서술한다.

```bash
python3 -m core.cli scenario \
  --destination "<목적지>" --period "YYYY-MM-DD~YYYY-MM-DD" \
  --persona "<페르소나>" --companions "<동행자>" --budget "<예산>" \
  --destination-iata "<IATA>"   # 있으면 항공까지 포함(없으면 항공은 skipped)
```
> 출력 `fixture.candidates`(정규화 상품), `fixture.edge_cases`(도메인 엣지케이스, 데이터 유도), `skipped`(누락 입력으로 못 부른 도메인 — 이 목록을 근거로 사용자에게 되묻는다), `errors`(도구 실패).
> 날짜는 `--period` 안의 ISO 날짜 2개를 자동 파싱한다. `--destination-iata`/`--depart-date`가 없으면 항공은 조용히 skip되고 stays/tnas는 계속 진행된다.

### 저수준: 개별 fetch (체이닝·디버깅용)
detail/availability 체이닝이나 단일 도구 확인이 필요하면 `fetch`를 직접 쓴다. `fetch`는 응답을 `ProductCandidate`로 정규화해 돌려준다:

```bash
python3 -m core.cli fetch searchTnas --args '{"query": "<목적지 키워드>"}'
python3 -m core.cli fetch searchStays --args '{"keyword": "<목적지>", "checkIn": "YYYY-MM-DD", "checkOut": "YYYY-MM-DD"}'
python3 -m core.cli fetch searchInternationalFlights --args '{"origin": "ICN", "destination": "<IATA>", "departDate": "YYYY-MM-DD"}'
# 상세/가용성 체이닝(둘 다 fetch):
python3 -m core.cli fetch getStayDetail --args '{"gid": <gid>, "checkIn": "...", "checkOut": "..."}'
python3 -m core.cli fetch getTnaOptions --args '{"gid": "<gid>", "url": "<url>", "selectedDate": "YYYY-MM-DD"}'
```
> 🚫 `.mcp.json` 의 `myrealtrip` 툴 직호출·`core.cli call`(raw)로 시나리오를 구성하지 말 것 — 디버깅 전용. 정규화는 반드시 `scenario`/`fetch` 경유.
> 인자명 주의: searchTnas 는 `query`, searchStays 는 `keyword`(+`checkIn`/`checkOut` 필수). 필수 누락 시 MCP `-32602` 오류.
> 인자 스키마가 불확실하면 `python3 -m core.cli list-tools-raw` 로 inputSchema 확인(디버깅).
> `scenario`는 `fetch` 출력의 `candidates[]` 조립 + 엣지케이스 유도(리뷰부족/가격변동/재고없음)를 `core.scenario.orchestrate`로 대신 수행한다. 수동 조립 시엔 `fetch` 출력을 `core.schema.scenario_fixture.ScenarioFixture` 로 모은다.

## 출력 (섹션)
1. **여행자 시나리오** — 항공/숙소/TNA 흐름 기반.
2. **실제 상품 후보** — 상품명·가격·가용성·평점·예약 URL (MCP 근거).
   > 예약 URL은 항공(`reservationUrl`)·TNA(product url)는 검색에서 바로 나오지만, **숙소는 검색(`searchStays`) 응답에 URL이 없다**(field_notes §3). 숙소 예약 링크·가용성·취소정책이 필요하면 해당 후보의 `gid`로 `getStayDetail`을 체이닝한다(→ `shareWebLink`).
3. **도메인 엣지 케이스** — 취소/환불/재고없음/날짜불일치/가격변동/리뷰부족/모바일.
   > **근거 있는 엣지만 서술한다.** 검색 깊이에서 증명되는 건 TNA/항공의 `mobile`·항공 `price_change` 정도이며, 취소/재고없음/날짜불일치는 `getStayDetail`/`getTnaOptions`/`getTnaDetail` 체이닝으로 증거가 확보됐을 때만 나타난다(field_notes §5). fixture `edge_cases`에 없는 엣지를 추측으로 덧붙이지 말 것.
4. **실험 초안** — 가설·지표·가드레일·실험군/대조군·실패조건.
5. **QA 초안** — 여행 도메인 QA 체크리스트 + E2E 아이디어.

## 보안 원칙
- 고객명·전화·이메일·예약번호·결제정보 입력 금지.
- 외부 MCP 호출 전 전송 데이터(키워드/날짜 등)를 사용자에게 명시.
