# B-03 세션 산출물 — 과제 A (scenario / 타이베이 3박4일 부모님 3인)

- 세션ID: B-03
- 과제: A(scenario)
- 참가자: PE-2
- 제출일: 2026-07-08 *(공개웹 재측정 — 07-07 MRT직접조회본 교체)*
- 조회 기준: 2026-07-08 15:33:29 KST. 소스: Kayak, Taipei 101 공식, Spring City Resort 공식, A Chef's Tour 공식, ExchangeRate-API. 환율 `1 USD = 1,516.90 KRW`, `1 TWD = 47.16 KRW`.
- 사용 도구: **공개 웹만.** `/mrt scenario`·MRT MCP·로컬 산출물 미사용 → **순수 baseline 통제조건 충족**(B-01과 동일 조건).
- 타임스탬프: **T0 15:14:08 · T1 15:18:26 · T2 15:30:17 · T3 15:33:29** (중단 0) → **전 구간 완비, 순 소요 산출 가능**

---

## [T0 | 15:14:08] 브리프 수령

## [T1 | 15:18:26] 문제 정의

해결할 마찰은 "해외여행이 익숙지 않은 60대 부모님 동행자가 항공·숙소·체험을 묶을 때, 가격보다 날짜 확정·예약 확정·동선 부담을 더 신뢰할 수 있게 판단하는가". 타깃은 인천 출발 타이베이 3박4일 가족 3인. 성공 기준은 1인 90만원 이하에서 새벽 이동·과도한 도보를 줄이고, 온천·야시장 대표 체험을 포함하되 각 상품의 예약 가능일·환불·현장예약 여부가 결제 전 명확히 드러나는 것.

## [T2 | 15:30:17] 시나리오 + 상품 근거

시나리오: ICN-TPE 직항/낮 시간 우선, 공개 가격은 Kayak 최저가를 예산 가드레일로. 숙소는 환승 최소화 위해 Taipei Main Station 인근 Cosmos Hotel Taipei 2실 기준. 1일차 도착·휴식, 2일차 베이터우 온천+Taipei 101, 3일차 16:00 야시장/푸드투어, 4일차 늦지 않은 귀국.

| # | 도메인 | 상품 | 가격 | URL(외부 소스) |
|---|---|---|---|---|
| 1 | 항공 | KAYAK ICN-TPE (Seoul Incheon→Taipei) | US$83 편도부터 (왕복 US$166/인 산정) | [Kayak](https://www.kayak.com/flight-routes/Seoul-Incheon-Intl-ICN/Taipei-Taiwan-Taoyuan-Intl-other-Airports-TPE) |
| 2 | 숙소 | Cosmos Hotel Taipei | US$76/night (2실×3박=US$456, 1인 US$152) | [Kayak](https://www.kayak.com/Taipei-Hotels-Cosmos-Hotel-Taipei.159690.ksp) |
| 3 | 투어 | A Chef's Tour — Taipei food tour | US$55/인 | [공식](https://achefstour.com/tour/taipei-food-tour) |
| 4 | 온천 | Spring City Resort Private Hot Spring | NT$600/adult | [공식](https://www.springresort.com.tw/en/fac/ins.php?index_id=2) |
| 5 | 전망대 | TAIPEI 101 General Ticket Adult | NT$600/adult | [공식](https://www.taipei-101.com.tw/en/observatory/ticket) |

예산 합산(1인): 항공 US$166 + 숙소 US$152 + 푸드투어 US$55 = US$373 ≈ **565,804원**. 온천 NT$600 + Taipei 101 NT$600 = NT$1,200 ≈ **56,589원**. 총 **약 622,393원/인**, 예산 900,000원 대비 약 **277,607원 여유.**

## [T3 | 15:33:29] 엣지케이스 + 실험/QA 초안

**엣지케이스 6개 전부 해당:**
- **취소/환불**: A Chef's Tour "24시간 전 취소 시 전액 환불" 명시. 반면 Spring City Resort는 전화예약 불가·현장 프런트 예약만 → 온천은 사전 확정/환불 흐름이 약함.
- **재고없음**: A Chef's Tour 최대 8명 소그룹·live calendar → 3인 동시 입장 및 10-09~12 가능일 결제 전 확인 필요. Spring City는 현장예약이라 도착 후 대기/마감 리스크.
- **날짜불일치**: Kayak 가격은 공개 SEO/구조화 데이터라 실제 10-09~12 결제가와 다를 수 있음. A Chef's Tour도 "date unavailable이면 연락" 명시.
- **가격변동**: Kayak "from"/priceRange 성격, A Chef's Tour 세금·booking fee 별도 가능. 환율도 조회 시점 기준이라 결제 통화 선택에 따라 총액 변동.
- **리뷰신뢰성**: Cosmos Hotel `8.6/10, 6,614 reviews` 구조화 데이터 있으나 출처·최근성·고령자 적합성 필터 없음. A Chef's Tour "99% 5-star across our tours"는 전체 투어 기준이라 해당 날짜/가이드 품질과 분리 필요.
- **모바일**: A Chef's Tour 예약은 Bokun live calendar 위젯+JS 필요("Please enable javascript" 문구) → 부모님 동행자가 모바일에서 확정 상태·수수료·취소 시점 놓칠 위험.

**실험 초안**: 상품 카드/번들 요약에 `예약확정 방식`·`날짜 가능 여부`·`환불`·`도보 부담`·`현장예약 리스크`를 배지로 한 화면 노출("확정성 패널"). 항공=날짜별 실가격 확인 필요, 숙소=2실 기준/3인 객실 미확정, 투어=live calendar/24h 환불, 온천=현장예약만. 가설: 부모 동행자의 결제 전 이탈·문의 감소. 성공지표 날짜 선택 후 결제 진입률·캘린더 품절 후 대체상품 클릭률·예약확정 CS 문의율·모바일 결제 완료율.

**QA 확인 항목**: 2026-10-09~12·성인 3명·모바일 375/390px·USD/TWD/KRW 환산·세금/수수료 문구·live calendar 품절 상태·환불 문구 충돌·2실 숙소 총액·온천 현장예약 경고·투어 시작/종료 위치와 도보 부담.

---

## 정합성 메모 (측정자 참고)

1. **순수 baseline 통제조건 충족** — 공개웹만 사용(B-01 재측정본2와 동일 조건). 과제 A baseline 두 데이터 포인트(B-01·B-03) 조건 정합.
2. **전 구간 타임스탬프 완비 + 중단 0** — 이 프로젝트 최초로 **주 지표 T3−T0(순 소요) 산출 가능**: **19분 21초**(1,161초). 구간: T1−T0 4:18 · T2−T1 11:51 · T3−T2 3:12.
3. **상품 근거가 외부 소스(Kayak/공식, USD·TWD)** — 파일럿(MRT/KRW) 비교 시 소스·통화 상이. 근거 정확도 검증은 해당 소스 재현으로.

## 품질 부지표 카운트

| 부지표 | 값 | 비고 |
|---|---|---|
| 도메인 엣지케이스 수 | **6** | 6개 전부 근거와 함께 명시 |
| 실제 상품 근거 수 | **5** | 5건 모두 상품명+가격+URL 충족(외부 소스) |
| 근거 정확도 | **미검증** | Kayak/공식 재현 검증 필요(`from`·priceRange·세전·환율 주의) |
