#!/usr/bin/env bash
# KRX Quant Assistant — Mac mini 초기 설정 스크립트
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_NAME="com.quant-krx.daily"
PLIST_SRC="${PROJECT_DIR}/ops/launchd/${PLIST_NAME}.plist.template"
PLIST_DST="${HOME}/Library/LaunchAgents/${PLIST_NAME}.plist"
LOGS_DIR="${PROJECT_DIR}/logs"
DATA_DIR="${PROJECT_DIR}/data"
REPORTS_DIR="${PROJECT_DIR}/reports"

echo "=== KRX Quant Assistant Setup ==="
echo "프로젝트 경로: ${PROJECT_DIR}"

# 1. 디렉토리 생성
mkdir -p "${LOGS_DIR}" "${DATA_DIR}" "${REPORTS_DIR}" "${PROJECT_DIR}/config"

# 2. uv 설치 확인
if ! command -v uv &>/dev/null; then
    echo "❌ uv가 없습니다. 설치: brew install uv"
    exit 1
fi
UV_PATH="$(which uv)"
echo "✅ uv: ${UV_PATH}"

# 3. Python 환경 확인
if ! uv run python --version &>/dev/null; then
    echo "❌ uv Python 환경이 없습니다. 실행: uv sync"
    exit 1
fi
echo "✅ Python: $(uv run python --version)"

# 4. watchlist.yaml 확인
if [ ! -f "${PROJECT_DIR}/config/watchlist.yaml" ]; then
    echo "⚠️  config/watchlist.yaml 없음 — config/watchlist.yaml.example 을 복사하세요"
fi

# 5. .env 파일 확인
if [ ! -f "${PROJECT_DIR}/.env" ]; then
    echo "⚠️  .env 없음 — .env.example 을 복사하고 API 키를 설정하세요:"
    echo "    cp .env.example .env && vim .env"
fi

# 6. launchd plist 설치
echo ""
echo "=== launchd plist 설치 ==="
sed \
    -e "s|__PROJECT_DIR__|${PROJECT_DIR}|g" \
    -e "s|__HOME_DIR__|${HOME}|g" \
    -e "s|/opt/homebrew/bin/uv|${UV_PATH}|g" \
    "${PLIST_SRC}" > "${PLIST_DST}"

echo "✅ plist 설치: ${PLIST_DST}"
echo "   환경변수(.env)를 plist에 직접 넣으려면 수동으로 편집하세요."

# 7. launchd 등록
if launchctl list "${PLIST_NAME}" &>/dev/null; then
    launchctl unload "${PLIST_DST}" 2>/dev/null || true
fi
launchctl load "${PLIST_DST}"
echo "✅ launchd 등록 완료: ${PLIST_NAME}"

# 8. dry-run 테스트
echo ""
echo "=== Dry-run 테스트 ==="
cd "${PROJECT_DIR}"
LLM_MOCK=true uv run python -m quant_krx run-daily --dry-run && echo "✅ dry-run 성공" || echo "❌ dry-run 실패 — 로그 확인: ${LOGS_DIR}/"

echo ""
echo "=== 설정 완료 ==="
echo "다음 실행 시각: 매일 15:35 KST (장 마감 후)"
echo "로그: ${LOGS_DIR}/launchd.stdout.log"
echo "수동 실행: cd ${PROJECT_DIR} && uv run python -m quant_krx run-daily --no-dry-run"
echo "스케줄 확인: launchctl list ${PLIST_NAME}"
