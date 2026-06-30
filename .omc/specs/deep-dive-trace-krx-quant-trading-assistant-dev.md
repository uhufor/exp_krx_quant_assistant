# Deep Dive Trace: krx-quant-trading-assistant-dev

## Observed Result
KRX 한국 주식 퀀트 트레이딩 어시스턴트 개발을 시작하려 하나, 이전 `.omx/` 세션의 계획 문서(spec, PRD, ralplan 컨센서스)를 새 `.omc/` 세션으로 이관하고, 실제 구현 착수를 위한 준비 상태를 점검해야 하는 상황.

## Ranked Hypotheses
| Rank | Hypothesis | Confidence | Evidence Strength | Why it leads |
|------|------------|------------|-------------------|--------------|
| 1 | 계획 문서는 내용적으로 완전하며 3가지 사전 결정 사항만 해결하면 즉시 구현 착수 가능 | High | Strong | Architect 2회 → APPROVE, Critic APPROVE. 10단계 구현 스텝 구체적이며 acceptance criteria 명확. 미결 항목은 VectorBT 버전, run_id 형식, 스토리지 선택 3가지뿐 |
| 2 | 세션 마이그레이션은 경로 문자열 업데이트만 필요한 기계적 작업 | High | Strong | 모든 파일이 순수 Markdown이며 내용 변경 불필요. `.omx/` → `.omc/` 경로 치환 + state JSON `spec_path` 연결이 전부 |
| 3 | 개발 환경은 완전히 미설치 상태이며 Python 인터프리터부터 모든 패키지를 새로 설치해야 함 | High | Strong | python3 = Xcode 3.9.6 (부적합), vectorbt/pandas/numpy/pykrx 등 0개 설치, uv/pyenv/conda 없음. Homebrew만 있음 |

## Evidence Summary by Hypothesis

### Hypothesis 1 — 계획 즉시 실행 가능 (3가지 사전 결정 제외)
- PRD의 10단계 구현 스텝은 올바른 순서로 배열되어 있고 각 단계의 입출력이 명확
- Step 1 acceptance criterion "config 로드 및 watchlist 검증 (네트워크 없이)"은 즉시 구현 가능
- 테스트 스펙이 PRD acceptance criteria 대부분과 1:1 대응
- Architect가 블로킹 이슈(Report A 경계, 알림 idempotency, 스케줄러 타임존 테스트)를 2회 반복으로 해결 후 APPROVE

### Hypothesis 2 — 세션 마이그레이션은 경로 치환만 필요
- `old-base-v1/` 하위 디렉토리 구조(`context/`, `interviews/`, `specs/`, `plans/`)가 원래 `.omx/` 구조와 1:1 대응
- 6개 파일 모두 순수 Markdown, 바이너리/직렬화 포맷 없음
- PRD 내 `.omx/plans/...` 경로 문자열이 론치 힌트 명령어와 JSON 블록에 포함됨
- `.omc/state/deep-interview-state.json`의 `spec_path: null` → 마이그레이션 후 연결 필요

### Hypothesis 3 — 환경 미설치
- `python3` → `/Applications/Xcode.app/.../python3` (3.9.6) — 프로젝트 용도 부적합
- `pip show vectorbt`, `pykrx`, `FinanceDataReader`, `duckdb`, `pandas`, `numpy` → 모두 NOT FOUND
- `pyenv`, `uv`, `conda`, `poetry` → 모두 없음
- `brew` 6.0.5 → 설치됨 (유일한 게이트웨이)
- 프로젝트 내 `pyproject.toml`, `requirements.txt` 없음, git 커밋 0개

## Evidence Against / Missing Evidence

### Hypothesis 1
- **Against**: VectorBT 버전 미지정 (free `vectorbt` vs 상용 `vectorbt-pro` — API가 다름)
- **Against**: `run_id` 형식 미정의 (Critic이 지적했지만 "optional follow-up"으로 남김)
- **Against**: 스토리지 선택(SQLite vs DuckDB) 미결 — Step 3 스키마 작업 전에 결정 필요
- **Missing**: 어댑터 전환 메커니즘 자체에 대한 통합 테스트 없음
- **Missing**: "최근 기간 수익률" 메트릭이 테스트 스펙 단위 테스트 매트릭스에서 누락

### Hypothesis 2
- **Against**: `.omx/` 경로 문자열이 PRD 론치 힌트 명령어(3곳)와 ralplan 컨센서스 JSON 블록(3곳)에 하드코딩됨
- **Missing**: OMC 워크플로(`$ultragoal`, `$team`)가 `spec_path` state 필드를 읽는지 CLI 인수로 받는지 불명확

### Hypothesis 3
- **Against (환경이 준비된 증거)**: Homebrew 6.0.5 설치됨, stdlib(ssl, sqlite3, urllib) 정상 작동
- **Against**: PyKrx, FinanceDataReader는 API 키 불필요 (공개 엔드포인트)
- **Missing**: Mac 아키텍처(arm64 vs x86_64) 미확인 — numba 바이너리 휠 가용성에 영향

## Per-Lane Critical Unknowns

- **Lane 1 (세션 마이그레이션)**: OMC 실행 워크플로가 PRD 경로를 `deep-interview-state.json`의 `spec_path` 필드에서 읽는지, 아니면 CLI 인수로 직접 전달받는지
- **Lane 2 (스펙 실행 가능성)**: 사용자가 상용 `vectorbt-pro` 라이선스를 보유하고 있는지, 아니면 무료 PyPI `vectorbt` 패키지를 사용하는지
- **Lane 3 (환경 전제조건)**: Mac이 Apple Silicon(arm64)인지 Intel(x86_64)인지 — numba 바이너리 휠 가용성과 Python 버전 요구사항에 직접 영향

## Lane 3 Misplacement / SoT Ownership Scope

해당 없음 — Lane 3은 환경 전제조건 갭 분석으로, 코드/파일 이동(MOVE) 시나리오가 아님.

## Rebuttal Round

- **Leader(H1)에 대한 최강 반론**: VectorBT 버전 선택 전에 executor가 Step 4 quant engine 코드를 작성하면, 잘못된 API로 작성된 모든 코드와 fixture를 재작업해야 함
- **Leader가 유지되는 이유**: 3가지 미결 항목(VectorBT 버전, run_id, 스토리지)은 짧은 사전 질문 세션으로 해결 가능. 내용 자체는 완전하고 컨센서스 승인됨. Step 1~2는 VectorBT와 무관하므로 즉시 착수 가능

## Convergence / Separation Notes

- H1(계획 완성도)과 H2(마이그레이션)는 독립적: 계획은 `.omx/` 경로 문자열과 무관하게 내용적으로 완전함
- H2(마이그레이션)와 H3(환경)은 순서가 있음: 환경 설치는 마이그레이션과 무관하게 병행 가능
- H1의 3가지 미결 항목(VectorBT, run_id, 스토리지)은 서로 독립적이지만 모두 Step 3~4 착수 전에 해결 필요

## Most Likely Explanation

이전 세션의 계획 문서는 내용 면에서 완전하고 컨센서스 승인이 완료된 상태다. 현재 세션 구성에는 세 가지 병렬 작업이 필요하다:
1. **마이그레이션**: `old-base-v1/` 파일의 `.omx/` 경로 문자열을 새 위치로 치환하고, state JSON에 `spec_path`를 연결
2. **환경 구성**: `brew install uv` → `uv python install 3.12` → `uv init` → 패키지 설치
3. **사전 결정 3건**: VectorBT 버전(free vs pro), run_id 형식, 스토리지(SQLite vs DuckDB) 결정

이 세 작업 후 Step 1 구현을 즉시 시작할 수 있다.

## Critical Unknown

**VectorBT 버전 선택** (free `vectorbt` PyPI vs 상용 `vectorbt-pro`). 이는 Step 4 quant engine의 임포트 경로, fixture 구조, 포트폴리오 시뮬레이션 API 전체에 영향을 미치는 이진 결정이다. 다른 미결 항목(run_id, 스토리지)은 executor가 합리적 기본값을 선택할 수 있지만, VectorBT 버전은 사용자의 라이선스 보유 여부에 달려 있어 외부 확인 없이 해결 불가능하다.

## Recommended Discriminating Probe

사용자에게 직접 질문: "vectorbt-pro 라이선스를 보유하고 계신가요, 아니면 무료 PyPI vectorbt를 사용하실 건가요?" — 이 답변 하나로 quant engine 코드 전체의 방향이 결정된다.
