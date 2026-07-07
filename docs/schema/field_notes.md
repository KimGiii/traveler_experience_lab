# MCP 응답 필드 노트 (검증 결과)

> 검증일: 2026-07-01 · 엔드포인트: `https://mcp-servers.myrealtrip.com/mcp` (무인증)
> 근거: [`../../fixtures/`](../../fixtures) 의 샘플 호출 산출물. 이 문서는 `ScenarioFixture` 스키마의 근거다.

## 0. 도구 인벤토리 (11개, `tools/list` 확인)
| 도메인 | 검색/독립 호출 | 체이닝(식별자 필요) |
|---|---|---|
| flights | `searchInternationalFlights`, `searchDomesticFlights`, `flightsFareCalendar`, `getPromotionAirlines` | — |
| stays | `searchStays` | `getStayDetail`(gid) |
| tnas | `getCategoryList`(city), `searchTnas`(query) | `getTnaDetail`(gid,url), `getTnaOptions`(gid,url,date) |
| util | `getCurrentTime` | — |

> 계획서 §5.1 대비 추가 확인: `getCategoryList`(searchTnas 전 권장), `getPromotionAirlines`.

## 1. 공통 응답 envelope
`tools/call` 결과는 항상 `result` 아래:
- `result.content[0].text` — **JSON 문자열**(항상 존재).
- `result.structuredContent` — 파싱된 객체. **flights/stays search 만 제공**. TNA·detail 계열은 없음 → `content[0].text` 를 JSON 파싱해야 함.
- `result.isError` — 오류일 때만 `true`.

### 실패 모드 2종 (둘 다 `ok=true`, `isError=true`)
1. **비즈니스 오류**: `structuredContent.success=false`, `error`(사람용 메시지), `presentation.note`. 예: `searchInternationalFlights` 필수 누락 → `"required input is missing. 누락: origin, departDate"`, `meta.status=400`.
2. **MCP 스키마 검증 오류**: `structuredContent` 없음, `content[0].text` 가 `MCP error -32602: Input validation error ...`. 예: `searchStays` 에서 `checkIn` 누락.

> 어댑터는 `isError` 와 `structuredContent.success` 를 **둘 다** 확인해야 한다.

## 2. Flights
`structuredContent.result` = `{ summary, items[], cheapest? }`, 상위에 `success/meta/presentation`.

`items[]` (intl 기준):
- `id`, `fareNo`, `tripType`(ONE_WAY|ROUND_TRIP), `airline`
- `route`: `{ origin, destination }` (IATA)
- `travelInfo`, `legs[]`: `{ legIndex, origin, destination, departDate(YYYYMMDD), departTime(HHMM), arriveDate, arriveTime, durationMinutes, stops, isDirect, segments[]{airlineCode,...} }`
- `price`: `{ currency: "KRW", total, breakdown:{baseAmount, discountedBaseAmount, taxAmount, tasfAmount} }`
- `isCheapest`, **`reservationUrl`** (예약 URL)
- `fareCalendar` 는 `result.cheapest`/`items[]` 에 `{departureDate,returnDate,airline,totalPrice}` — **실시간 아님**(presentation.note 명시), 가격 변동 엣지케이스 근거.

## 3. Stays
### searchStays → `structuredContent`
- `stays[]`: `{ gid(int), name, description, price(str "86,834원~"), additionalPrice, rating(float), reviewCount(str), tags[], thumbnailUrl, wishCount }`
- `searchParams`, `pagination:{currentPage,hasNextPage,totalCount,itemsInThisPage}`
- `content[0].text` 는 데이터가 아니라 **위젯 UI 트리** → 무시하고 structuredContent 사용.

### getStayDetail → `content[0].text`(JSON)
`{ success, searchParams, property, pricing, location, amenities, reviews, rooms[], roomCount, noRoomsAvailable }`
- `property`: `{ gid, gpid, name, grade, category, region, reviewScore, reviewCount, images[], shareWebLink }`
- `pricing`: `{ isSoldOut, priceLabel, priceText, averagePrice(int), totalPrice(int), originalPrice, originalPriceText }` ← **재고없음/가격변동 엣지케이스**
- `rooms[]`: `{ roomName, roomId, providerRoomId, images, urgentNotice, attributes, ratePlan, isFreeCancellation }` ← **취소정책 엣지케이스**
- `noRoomsAvailable`(bool) ← 재고없음 엣지케이스

## 4. TNA (Tours & Activities)
### searchTnas → `content[0].text`(JSON), structuredContent 없음
`{ widget(UI 트리), name, copy_text }`
- **상품 데이터는 `copy_text`(모델용 마크다운)** 에 존재: 순위·상품명·⭐평점·시작가(`84,000원~`)·총건수.
- 상품 URL(`https://experiences.myrealtrip.com/products/<gid>`)은 `widget` 내부에 임베드 → **gid 는 URL 말미 숫자**로 추출.
- getTnaDetail/getTnaOptions 체이닝에 이 gid+url 필요.

### getCategoryList → `content[0].text`(JSON)
`{ success, searchParams:{city}, categories[]:{name,value,isSelected} }` — searchTnas `category` 값의 출처(추측 금지).

### getTnaDetail → `content[0].text`(JSON)
`{ widget, name, copy_text }` — `copy_text` 에 상품명·평점·리뷰수·포함/불포함 사항 마크다운.
⚠️ 취소정책은 **상품별로 있을 수도 없을 수도** 있음(검증한 6082857 응답엔 미포함). 어댑터는 `취소/환불` 문구가 있을 때만 `cancellation_note` 채움.

### getTnaOptions → `content[0].text`(JSON)
`{ success, searchParams, selectedDate, isRequestedDateAvailable, hasAvailableOptions, availabilityMessage, units[], options[], defaultOption }`
- **실측 엣지케이스**: 2026-09-11 조회 시 `isRequestedDateAvailable=false, hasAvailableOptions=false, availabilityMessage="해당 날짜는 예약이 불가능합니다.", options=[]` ← 날짜불일치/재고없음 근거.

## 5. 엣지케이스 → 근거 필드 매핑 (scenario 출력용)
| 엣지케이스 | 근거 필드 |
|---|---|
| 재고없음 | stay `pricing.isSoldOut`/`noRoomsAvailable`, tna `hasAvailableOptions=false` |
| 날짜불일치 | tna `isRequestedDateAvailable=false`, `availabilityMessage` |
| 가격변동 | flight fareCalendar `note`(실시간 아님), stay `originalPrice` vs `averagePrice` |
| 취소/환불 | stay room `isFreeCancellation`/`ratePlan`, tna detail `copy_text` 취소정책 |
| 리뷰부족/신뢰성 | stay `reviewCount`, tna `copy_text` ⭐/리뷰수 |
| 모바일 | 모든 예약 URL(`reservationUrl`, `shareWebLink`, product url) 은 모바일 웹 |

## 6. 미해결/후속
- searchTnas 상품별 **정형 필드(gid/price/rating)** 는 structuredContent 미제공 → `copy_text` 파싱 or widget 트리 파서 필요. 현재 어댑터는 URL→gid + copy_text 기반 최소 추출.
- 레이트리밋: 이번 스윕(총 13콜) 정상. 대량 fixture 생성 시 별도 측정 필요(계획서 §7).
- `passengers` 등 object 인자 세부 스키마는 미검증(기본값 동작 확인만).
