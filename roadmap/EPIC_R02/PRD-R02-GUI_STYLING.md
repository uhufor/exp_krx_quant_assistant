# Deep Interview Spec: EPIC-R02 GUI Mantine 스타일링/UX 개선

## Metadata
- Interview ID: epic-r02-gui-mantine-20260719
- Rounds: 4 (+ Round 0 토폴로지 확인)
- Final Ambiguity Score: 14.45%
- Type: brownfield
- Generated: 2026-07-19
- Threshold: 0.2 (20%)
- Threshold Source: default
- Initial Context Summarized: no
- Status: PASSED

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.88 | 35% | 0.3080 |
| Constraint Clarity | 0.80 | 25% | 0.2000 |
| Success Criteria | 0.88 | 25% | 0.2200 |
| Context Clarity | 0.85 | 15% | 0.1275 |
| **Total Clarity** | | | **0.8555** |
| **Ambiguity** | | | **0.1445** |

## Topology

| Component | Status | Description | Coverage |
|-----------|--------|-------------|----------|
| Mantine 기반 설치/설정 | active | `MantineProvider`, 라이트/다크 테마 + 전환 토글, 색상/폰트/스페이싱 구성 | Acceptance Criteria 반영 |
| 네비게이션/전역 레이아웃 | active | `App.tsx`의 단순 탭 네비게이션을 Mantine 레이아웃 컴포넌트로 교체 | Acceptance Criteria 반영 |
| 폼/입력 컴포넌트 전환 | active | 공식·규칙·전략·백테스트 폼 전체의 raw HTML input/select/button → Mantine 컴포넌트 | Acceptance Criteria 반영 |
| 트리 편집기 시각화 | active | Formula/Rule 재귀 트리의 계층 구조를 카드 경계·들여쓰기로 명확히 표현 | Acceptance Criteria 반영 |
| 데이터 표시 컴포넌트 | active | 팩터 목록, 백테스트 지표·거래내역 테이블, equity curve 차트 영역 | Acceptance Criteria 반영 |
| 피드백/상태 표시 | active | 저장/삭제 등 짧은 결과=토스트, 검증 오류 등 긴 목록=인라인 배너 | Acceptance Criteria 반영 |

## Goal

기존 EPIC_R02 GUI(React+Vite, 인라인 `style={{}}` 57회 산재, 컴포넌트 라이브러리 전무, 화면 요소 간
시각적 경계·간격이 없어 사용성이 떨어짐)에 **Mantine**(mantine.dev) UI 프레임워크를 도입해 6개
화면(팩터/공식/규칙/전략/백테스트/네비게이션)의 스타일링과 UX를 일관되게 개선한다. 라이트/다크
테마 전환을 지원하고, 성공·오류 피드백을 상황에 맞게(짧은 결과=토스트, 긴 검증오류=인라인 배너)
표시한다. 기존 상태관리·API 호출·검증 흐름 등 **기능 동작은 변경하지 않으며**, 순수 프레젠테이션
계층 개선이 목표다(단, Mantine 네이티브 컴포넌트가 더 적합하면 내부 구조 개선은 허용).

## Constraints

- **기능 무변경**: 기존 로직(상태관리, `/api/*` 호출, 검증·저장·활성화·Export/Import·백테스트 흐름)은
  동작상 동일해야 한다. 순수 시각적 교체가 기본이며, 구조 개선이 필요한 경우(예: 트리 편집기에
  Mantine 네이티브 컴포넌트 활용)에도 최종 사용자 관점의 기능은 보존한다.
- **다크모드 필수**: 라이트/다크 테마 모두 지원 + 사용자가 전환할 수 있는 토글 제공(Mantine
  `color-scheme` 기능 그대로 활용).
- **완료 확인 프로세스**: 나는 브라우저 스크린샷을 직접 찍을 수 없다(도구 제약). 완료 확인은
  사용자가 `npm run dev`로 직접 확인 후 피드백을 주는 반복 사이클로 진행한다 — 한 번에 "완성"을
  주장하지 않고, 단계별로 사용자 검토를 받는다.
- **작업 범위**: 필요시 구조 개선 허용(순수 스타일 교체보다 넓은 재량 — 예: 태그 입력을 Mantine
  `TagsInput`으로, 트리 편집기 레이아웃을 Mantine `Tree`/`Paper`/`Stack` 조합으로 재설계 가능).
- **회귀 없음**: 기존 백엔드 pytest 스위트(583개)는 영향받지 않아야 한다(프론트엔드 전용 작업).
  기존 프론트엔드 Vitest(6건, 트리 순수 로직 검증)는 구조 변경 시 갱신하되 통과 상태를 유지한다.
- 기술스택은 이미 확정된 React 19.2.7 + Vite 8.1.1 + TypeScript 위에 Mantine을 추가하는 것으로,
  프레임워크 자체를 교체하지 않는다.

## Non-Goals

- 백엔드 API·데이터 계약 변경(이번 작업은 순수 프론트엔드 프레젠테이션 계층).
- 신규 기능 추가(기존 화면·기능의 시각적 개선만, 새 화면/엔드포인트 없음).
- 모바일/반응형 레이아웃 최적화(로컬 1인용 데스크톱 도구 전제 유지 — GUI PRD-R01의 "로컬 1인용"
  제약과 정합. 필요해지면 별도 요청으로 다룬다).
- 자동화된 시각적 회귀 테스트(Playwright 스크린샷 비교 등) 도입 — 완료 확인은 사용자 수동 검토로
  대체(위 Constraints 참고).

## Acceptance Criteria

- [ ] `MantineProvider`가 앱 최상위에 적용되고, 라이트/다크 테마 전환 토글이 동작한다.
- [ ] `App.tsx`의 탭 네비게이션이 Mantine 레이아웃/네비게이션 컴포넌트로 교체되어 현재 탭이
      시각적으로 명확히 구분된다.
- [ ] 팩터/공식/규칙/전략/백테스트 5개 페이지의 모든 raw HTML `<input>`/`<select>`/`<button>`이
      Mantine 대응 컴포넌트(`TextInput`/`NumberInput`/`Select`/`Button` 등)로 교체된다.
- [ ] Formula/Rule 트리 편집기의 중첩 노드가 카드 경계·들여쓰기로 시각적 계층을 명확히 표현한다.
- [ ] 팩터 목록, 백테스트 지표 요약·거래내역이 Mantine `Table`로, equity curve 차트가 카드/구획
      안에 시각적으로 정리되어 표시된다.
- [ ] 저장/삭제/활성화 등 짧은 성공·오류 결과는 토스트 알림(Mantine `notifications`)으로,
      검증(validate) 오류 목록처럼 긴 내용은 인라인 Alert 배너로 표시된다.
- [ ] 기존 CRUD·검증·활성화·템플릿·Export/Import·백테스트 실행의 **기능 동작이 스타일링 전과
      동일**하다(수동 확인).
- [ ] `cd web && npm run build`(tsc+vite build)와 `npm test`(Vitest)가 통과한다.
- [ ] `uv run pytest tests/ -q`(백엔드 583개)가 영향받지 않고 통과한다.
- [ ] 각 주요 단계 완료 시 사용자가 `npm run dev`로 직접 검토하고 피드백하는 반복 사이클을 거친다.

## Assumptions Exposed & Resolved

| Assumption | Challenge | Resolution |
|------------|-----------|------------|
| 다크모드는 있으면 좋은 정도(nice-to-have)다 | 테마 구성(색상 팔레트 설계)이 다크모드 지원 여부에 따라 크게 달라짐을 제시 | 라이트/다크 모두 필수 + 전환 토글 확정 |
| 완료 여부는 AI가 스스로 "다 됐다"고 판단할 수 있다 | 브라우저 스크린샷을 찍을 도구가 없다는 실제 제약을 제시 | 사용자가 `npm run dev`로 직접 확인 후 피드백하는 반복 사이클로 확정 |
| 기존 상태관리/로직 구조를 100% 그대로 유지해야 한다 | 순수 시각적 교체 vs 구조 개선 허용 범위를 질문 | 필요시 구조 개선 허용(Mantine 네이티브 컴포넌트 활용 가능)으로 확정 — 단, 기능 동작은 불변 |
| 모든 피드백 메시지는 같은 방식(토스트 또는 배너)으로 통일해야 한다 | 짧은 결과와 긴 검증오류 목록의 UX 요구가 다름을 제시 | 상황별 구분(짧은 결과=토스트, 긴 목록=인라인 배너)으로 확정 |

## Technical Context

- 현재 프론트엔드: `web/src/pages/`(FactorsPage, FormulaBuilderPage, RuleBuilderPage,
  StrategyBuilderPage, BacktestPage), `web/src/tree/`(OperandEditor, FormulaTreeEditor,
  RuleTreeEditor), `web/src/App.tsx`(탭 네비게이션), `web/src/api/`(client.ts, hooks.ts).
  총 1652줄, 인라인 `style={{}}` 57회, 컴포넌트 라이브러리 없음.
- 의존성: React 19.2.7, Vite 8.1.1, TypeScript ~6.0.2, `recharts`(equity curve 차트),
  `vitest`(순수 로직 테스트 6건).
- Mantine 후보 패키지(구현 단계에서 확정): `@mantine/core`+`@mantine/hooks`(필수, 컴포넌트+
  color-scheme 훅), `@mantine/notifications`(토스트), `@mantine/charts`(recharts 래퍼 —
  기존 `recharts` 의존성과 호환되며 Mantine 테마와 통합되는 자연스러운 선택지, 최종 채택 여부는
  실행 단계에서 결정).
- 백엔드는 이번 작업과 무관(변경 없음) — `src/quant_krx/api/` 전혀 손대지 않음.

## Interview Transcript
<details>
<summary>Full Q&A (4 rounds + Round 0)</summary>

### Round 0 (토폴로지 확인)
**Q:** 6개 컴포넌트(Mantine 설정, 네비게이션, 폼전환, 트리편집기, 데이터표시, 피드백표시)로 이해했는데 맞는지?
**A:** "맞습니다, 그대로 진행"

### Round 1
**Q:** 다크모드를 지원해야 하나요?
**A:** "라이트/다크 모두 지원 + 전환 토글(추천)"
**Ambiguity:** 39.75% (Goal: 0.75, Constraints: 0.5, Criteria: 0.35, Context: 0.85)

### Round 2
**Q:** 스타일링 작업이 끝난 뒤 완료 확인은 어떻게 진행할까요?
**A:** "사용자가 npm run dev로 직접 확인 후 피드백(추천)"
**Ambiguity:** 29.25% (Goal: 0.8, Constraints: 0.5, Criteria: 0.7, Context: 0.85)

### Round 3
**Q:** 스타일링 작업 범위를 어느 수준으로 원하시나요?
**A:** "필요시 구조 개선도 허용"
**Ambiguity:** 21.05% (Goal: 0.82, Constraints: 0.75, Criteria: 0.75, Context: 0.85)

### Round 4
**Q:** 저장/삭제/검증 결과 같은 성공·오류 메시지를 어떻게 보여줘야 할까요?
**A:** "둘 다(상황별 구분)"
**Ambiguity:** 14.45% (Goal: 0.88, Constraints: 0.8, Criteria: 0.88, Context: 0.85) → **임계값(20%) 이하 도달**

</details>
