# 파일럿 실측 기록 시트 (플러그인 사용)

- 준비일: 2026-07-09 · 상태: **실측 대기**
- 과제: [`pilot_task_briefs.md`](../baseline/pilot_task_briefs.md) (A′ 방콕 / B′ voc-025~033)
- 비교 기준: [`baseline_sheet.md`](../baseline/baseline_sheet.md) · [`baseline_report.md`](../baseline/baseline_report.md)
- 스키마는 baseline_sheet와 동형. **참가자는 baseline과 동일 인물(PE-1~3, within-subject)** 권장.

> ⚠ 운영 주의 (기록 전 읽을 것)
> - T0~T3 **네 시각을 서로 다르게** 기록 (`YYYY-MM-DD HH:MM:SS KST`). 동일 시각 금지 — baseline 반복 실패.
> - `/mrt scenario`에 **`--adults 3` 필수** (A′). `_meta.warnings` 있으면 비고에 그대로 기록.
> - PE 3명 **세션 시작 2~3분 시차** (레이트 리밋). 429 재시도 대기 발생 시 비고에 기록.
> - B′ 채점은 [축 경계 가이드](../voc/axis-guide.md) 기준. 정답 축은 pilot_task_briefs B′-3.

## 세션 기록

| 세션ID | 일자 | 참가자 | 과제 | T0 | T1 | T2 | T3 | 중단(분) | 순 소요(분) | 엣지케이스 수 | 상품 근거 수 | 비고 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P′-01 | | PE-1 | A′(scenario·방콕) | | | | | | | | | |
| P′-02 | | PE-1 | B′(diagnose·9건) | | | | | | | | | |
| P′-03 | | PE-2 | A′(scenario·방콕) | | | | | | | | | |
| P′-04 | | PE-2 | B′(diagnose·9건) | | | | | | | | | |
| P′-05 | | PE-3 | A′(scenario·방콕) | | | | | | | | | |
| P′-06 | | PE-3 | B′(diagnose·9건) | | | | | | | | | |

## 구간별 분해 (보조 지표)

| 세션ID | T1−T0 (문제 정의) | T2−T1 (근거 수집) | T3−T2 (실험/QA 초안) |
|---|---|---|---|
| P′-01 | | | |
| P′-02 | | | |
| P′-03 | | | |
| P′-04 | | | |
| P′-05 | | | |
| P′-06 | | | |

> baseline 관찰: 과제 A는 **T2−T1(근거 수집)이 최중량 구간**(중앙값 7:24) — 플러그인 효과가 나타나야 할 곳.

## 판정 (A′ 3세션 완료 시 기입)

| 지표 | baseline | 파일럿 목표 | 파일럿 실측 | 판정 |
|---|---|---|---|---|
| A′ 순 소요 중앙값 | 8분 20초 | **≤ 4분 10초** | | |
| A′ 엣지케이스 수 중앙값 | 6 | ≥ 6 | | |
| A′ 상품 근거 수 중앙값 | 5 | ≥ 5 | | |
| B′ 분류 정확도(3축, 비율) | ≈52% (12.5/24) | ≥ 52% (x/9 비율 비교) | | |

- 판정 규칙: **A′ 시간 목표 달성 AND 품질 2지표 유지** → 계획서 §9 1차 성공지표 달성. B′는 품질 참고 판정(시간 제외, A안).
- 해석 시 명시할 caveat (3건, [baseline_report §6](../baseline/baseline_report.md)):
  1. 근거 정확도는 파일럿(MRT, 전량 재검증 가능)이 baseline(외부 웹, OTA 봇 차단으로 검증 불가)보다 구조적으로 유리.
  2. B′ 정확도 상승분에는 축 경계 가이드 효과가 섞임 (baseline은 가이드 없이 측정).
  3. B′는 약한 동형 (9건 vs 24건, 리뷰 신뢰성 축 편향) — 비율 비교만.
- 확정일:

## CSV (도구 처리용 — 위 표와 동일 스키마)

```csv
session_id,date,participant,task,t0,t1,t2,t3,interrupt_min,net_min,edge_case_count,product_evidence_count,note
P'-01,,PE-1,A',,,,,,,,,
P'-02,,PE-1,B',,,,,,,,,
P'-03,,PE-2,A',,,,,,,,,
P'-04,,PE-2,B',,,,,,,,,
P'-05,,PE-3,A',,,,,,,,,
P'-06,,PE-3,B',,,,,,,,,
```
