# Traveler Experience Lab — 플러그인 기획 계획서

> 마이리얼트립 Product Engineer(PE)가 여행자 경험 문제를 **실시간 상품 인벤토리 + 실제 VoC**로 근거화하여
> 문제 정의부터 구현 브리프까지 얇고 날카롭게 정리하도록 돕는 플러그인.

- **문서 상태**: 방향 확정 (scenario-first MVP)
- **타깃 런타임**: **Codex-first, Claude-compatible 듀얼 런타임** — 런타임 무관 공용 코어(`core/`)를 Codex(`.codex-plugin/`, `skills/`, `.mcp.json`)와 Claude Code(`.claude-plugin/`)가 얇게 공유. (구현 시 듀얼로 확정, 2026-07-02)
- **최종 수정**: 2026-07-02

---

## 1. 배경 & 조사 요약

### 1.1 사업 분야 / 모델
- 항공권·숙박·투어&액티비티·렌터카·유심 등을 한 플랫폼에서 예약하는 **TSA(Travel Super App)** 지향.
- 직접 판매가 아닌 **중개 수수료 기반** 플랫폼.
- 최근 확장: 럭키글라이드(항공가 스캐너), 리셀마켓(여행상품 양도), 플라이보드(실시간 공항정보).
- 출처: [나무위키](https://namu.wiki/w/%EB%A7%88%EC%9D%B4%EB%A6%AC%EC%96%BC%ED%8A%B8%EB%A6%BD), [THE VC](https://thevc.kr/myrealtrip)

### 1.2 업무 수행 방식 (플러그인이 붙을 지점)
- 2025년 8월, 개발자·디자이너·PM 구분을 없애고 약 70명을 **Product Engineer(PE)** 로 재편.
- PE는 **문제 정의 → 구현 → 배포**를 end-to-end로 책임 (프론트/백 구분 없음).
- 전 구성원 **AI 도구 약 30종 무제한 지원**, 월간 기수제 **AI 챔피언 프로그램** 운영.
- 출처: [벤처스퀘어](https://www.venturesquare.net/1062378), [How we build MyRealTrip](https://medium.com/myrealtrip-product/)

### 1.3 여행자 경험 페인포인트 (VoC)
| 문제 | 내용 |
|---|---|
| CS 단절 | 전화 미연결, 이메일/1:1 문의 부재, 채팅 상담사 연결 지연 |
| 확정 지연 | 예약 확정 메일 지연, 거래처 무응답, 사후 취소 안내 |
| 환불 지연 | 환불 프로세스 1주일+ 소요 |
| 리뷰 신뢰성 | 부정적 후기 삭제 → 평점 인플레이션(4.8~5.0 집중) |
| 취소 정책 | '취소보장'도 90% 전자바우처 환급, 전액 현금환불 아님 |
| 긴급 대응 | 야간/주말 긴급상황 즉각 대응 불가 |

출처: [블라인드](https://www.teamblind.com/kr/post/%EB%A7%88%EC%9D%B4%EB%A6%AC%EC%96%BC%ED%8A%B8%EB%A6%BD-%EC%A7%84%EC%A7%9C-%ED%99%94%EB%94%B1%EC%A7%80%EB%82%98%EB%84%A4%E3%85%8B%E3%85%8B%E3%85%8B-ETpAU0ow), [브런치](https://brunch.co.kr/@leedonggun/20)

---

## 2. 핵심 문제 정의 (Job-to-be-Done)

> "여행자 경험에서 발견한 마찰을 실제 제품 변경으로 만들기 전에,
> **실시간 상품 맥락**과 **실제 여행자 불만**을 근거로 문제 정의·시나리오·구현 브리프를 빠르게 정리하고 싶다."

**차별화 논거**: PE는 이미 Cursor/Codex 등 30종 AI 도구를 쓴다. 따라서 플러그인의 존재 이유는
**"범용 LLM이 못 하는 것"**, 즉 ① **실시간 MRT 상품 인벤토리 접근**, ② **실제 MRT VoC 데이터** 두 가지에만 있다.

---

## 3. 전략적 판단 (VoC Insight vs Traveler Experience Lab)

| 축 | VoC Insight (초기안) | **Traveler Experience Lab (채택)** |
|---|---|---|
| 성격 | 방어적·회고적 | 생성적·전방위 |
| PE 워크플로우 적합성 | 개발 직전 일부 | **end-to-end 전체** |
| 고유 moat | 실제 여행자 불만(VoC) | **실시간 상품 인벤토리(MCP)** + VoC |
| 조직문화 적합성 | 보통 | 높음 (PE 오너십과 정확히 매핑) |

**결론**: TEL 비전을 채택하되, 두 안의 해자만 뽑아 **2개 명령어 wedge**로 압축한다.
`experiment`/`qa`/`release`는 범용 LLM으로도 되는 커모디티이므로 **독립 명령어로 만들지 않고 출력 섹션으로 강등**한다.
(명령어가 많아질수록 "왜 Cursor 프롬프트가 아니라 플러그인인가?"에 취약해진다.)

---

## 4. MVP 범위 — 2개 명령어 wedge

### 4.1 `/mrt scenario` (1순위, 즉시 파일럿 가능)
- **근거**: MCP 상품 인벤토리가 실동작 → 범용 LLM/Cursor 대비 차별점이 가장 분명.
- **입력**: 목적지, 여행 기간, 예산, 동행자, 목적/페르소나.
- **출력**:
  - 항공/숙소/TNA 기반 여행자 시나리오
  - 실제 상품 후보 (상품명·가격·가용성·평점·예약 URL)
  - 도메인 엣지 케이스 (취소/환불/재고없음/날짜불일치/가격변동/리뷰부족/모바일)
  - 실험 초안 + QA 초안 (← experiment/qa를 섹션으로 흡수)

### 4.2 `/mrt diagnose` (2순위, VoC 접근 확인 후)
- **근거**: 실제 CS/리뷰 데이터가 없으면 "그럴듯한 여정 분류"에 그침 → 0주차 검증 게이트에 종속.
- **입력**: 비식별 VoC 요약 (CS/리뷰/커뮤니티).
- **출력**: VoC → 여정 단계 → 마찰 유형 → 심각도/빈도 → 연결 가능한 상품 시나리오(`scenario`로 핸드오프).

### 4.3 출력 섹션으로 강등 (독립 명령어 아님)
- `experiment`: 가설·지표·가드레일·실험군/대조군·실패조건 → scenario/diagnose 출력에 포함.
- `qa`: 여행 도메인 QA 체크리스트 + E2E 아이디어 → scenario 출력에 포함.
- `release`: 롤백·고객 커뮤니케이션·CX 영향 체크리스트 → scenario 출력에 포함.

---

## 5. 데이터 / 도구 연결

### 5.1 MCP (검증 완료 ✅)
- 엔드포인트: `https://mcp-servers.myrealtrip.com/mcp` — **별도 인증 없이 공개**.
- 프로토콜: JSON-RPC over HTTP POST (`GET`은 405 "POST only" 반환).
- 검증 결과 (2026-07-01):
  - `initialize`, `tools/list`, `tools/call` 모두 `200`.
  - `tools/list` → `getCurrentTime`, `searchStays`(상세 inputSchema), `getStayDetail`, `searchTnas` 등 반환 확인.
  - `searchTnas` "오사카 유니버설 스튜디오" → 실제 상품명·가격·평점·예약 URL 수신.
  - 문서 일치: [MCP 개요](https://docs.myrealtrip.com/#/api/mcp/overview), [MCP 제공 도구](https://docs.myrealtrip.com/#/api/mcp/tools)
- 사용 도구(초기): `searchStays`/`getStayDetail`, `searchDomesticFlights`/`searchInternationalFlights`/`flightsFareCalendar`, `searchTnas`/`getTnaDetail`/`getTnaOptions`.

### 5.2 VoC (0주차 검증 게이트)
- 사내 CS/리뷰/커뮤니티 요약 데이터 접근권 확인 필요.
- **비식별 요약만** 사용. 원문·PII 반입 금지.

---

## 6. 보안 / 개인정보 원칙
- 고객명·전화·이메일·예약번호·결제정보 **입력 금지**.
- VoC는 **비식별 요약**만 사용.
- 외부 MCP 호출 전 **전송 데이터 명시**.
- 내부 정책/코드는 로컬 컨텍스트에서만 사용, 외부로 원문 전송하지 않는 모드 제공.

---

## 7. 리스크 & 게이트

| 리스크 | 상태 | 대응 |
|---|---|---|
| MCP 엔드포인트 실재 | ✅ 해소 (검증 완료) | — |
| MCP 응답 품질/필드 충분성 | 🔶 미확인 | 항공/숙소/TNA 각 3개 샘플 호출로 필드·실패케이스 확인 |
| MCP 레이트 리밋 | 🔶 미확인 | fixture 생성이 실트래픽에 주는 부담 측정 |
| VoC 접근권/비식별/품질 | 🔶 조건부 해소 (2026-07-06) | 공개 VoC 비식별 요약 33건 확보([게이트 판정](docs/voc/0-week-gate.md), `fixtures/voc/`) → diagnose 파일럿 가능. 사내 데이터 접근권은 미확인 — 확보 시 교체 |
| 성공지표 baseline 부재 | 🟢 과제 A 실측 완료 / 과제 B 품질만 (2026-07-08) | PE 3명 × 6세션 순수 공개웹 실측([결과 리포트](docs/baseline/baseline_report.md)·[시트](docs/baseline/baseline_sheet.md)). **과제 A 순 소요 중앙값 8분20초** → 파일럿 목표 ≤4분10초. 과제 B는 시간 무효(24건 분류가 수십 초로 찍힘)로 **품질(분류 정확도 3축 12.5/24)만** 사용(A안). |

**Go/No-Go**: MCP는 게이트에서 내려옴. 이제 승부처는 **"실시간 인벤토리 시나리오 + 실제 VoC"를 얼마나 얇고 날카롭게 묶느냐**.

---

## 8. 빌드 순서 & 다음 1주 액션

**순서: scenario-first → diagnose-second.**

1. 항공/숙소/TNA 각각 3개 샘플 호출 → 응답 필드·실패 케이스 확인.
2. MCP 응답을 `ScenarioFixture` 형태로 정규화하는 어댑터 설계.
3. ~~VoC 샘플 30~50건을 비식별 요약으로 받을 수 있는지 확인 (0주차 게이트).~~ → 🔶 공개 VoC 33건으로 조건부 통과 (2026-07-06, [판정 기록](docs/voc/0-week-gate.md)).
4. ~~PE 2~3명에게 현재 "문제→시나리오→실험 브리프" 작성 소요시간 **baseline 측정**.~~ → ✅ **6세션 실측 완료 (2026-07-08)**. 과제 A 확정(순 소요 중앙값 8분20초), 과제 B 품질만. [결과 리포트](docs/baseline/baseline_report.md)·[동형 파일럿 과제](docs/baseline/pilot_task_briefs.md).
5. 타깃 런타임 **Codex-first + Claude-compatible 듀얼**로 고정 (공용 코어 `core/` + 양쪽 얇은 어댑터).

---

## 9. 성공 지표
- PE의 "문제→이슈/PRD 정리 시간" 50%↓ — **baseline 확정(2026-07-08): 과제 A 순 소요 중앙값 8분20초 → 목표 ≤4분10초** (품질 엣지≥6·상품≥5 유지 조건). 과제 B는 품질(분류 정확도)만 판정.
- 신규 기능/실험당 생성되는 도메인 엣지 케이스 수 증가.
- QA/리뷰 단계에서 발견되는 여행 도메인 누락 감소.
- 항공+숙소+TNA 복합 시나리오 테스트 작성률 증가.
- 파일럿 사용자 주간 재사용률.

---

## 10. 제외 범위 (MVP)
- 실제 예약/결제 실행.
- 개인정보 포함 CS 원문 처리.
- 내부 지표 자동 조회.
- 자동 배포/운영 액션.
