from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from quant_krx._jsonnorm import DefinitionError
from quant_krx.factors.errors import FactorError, ParamValidationError, UnknownFactorError
from quant_krx.screening import errors as screening_errors
from quant_krx.workspace.errors import WorkspaceError


class NotFoundError(Exception):
    """라우터가 get_*(id) -> None을 받았을 때 사용하는 404 표시 오류(not_found_hint 메시지 보존)."""


def _detail(exc: Exception) -> dict[str, str]:
    # WorkspaceError/UnknownFactorError 메시지(not_found_hint 포함)를 재작성하지 않고 전달한다.
    return {"detail": str(exc)}


async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content=_detail(exc))


async def unknown_factor_handler(request: Request, exc: UnknownFactorError) -> JSONResponse:
    return JSONResponse(status_code=404, content=_detail(exc))


async def param_validation_handler(request: Request, exc: ParamValidationError) -> JSONResponse:
    return JSONResponse(status_code=400, content=_detail(exc))


async def factor_error_handler(request: Request, exc: FactorError) -> JSONResponse:
    return JSONResponse(status_code=400, content=_detail(exc))


async def definition_error_handler(request: Request, exc: DefinitionError) -> JSONResponse:
    # Formula/Rule/Strategy 정의 파싱·직렬화·다운그레이드 오류(from_dict/to_dict 경로).
    return JSONResponse(status_code=400, content=_detail(exc))


async def workspace_error_handler(request: Request, exc: WorkspaceError) -> JSONResponse:
    # 활성 참조 차단·검증 실패 등 도메인 규칙 위반 — 409 Conflict(요청 자체는 well-formed).
    return JSONResponse(status_code=409, content=_detail(exc))


async def screening_empty_universe_handler(
    request: Request, exc: screening_errors.EmptyUniverseError
) -> JSONResponse:
    # 필터 적용 후 스캔 유니버스가 비어 실행 결과가 성립하지 않는 도메인 조건 — 409.
    return JSONResponse(status_code=409, content=_detail(exc))


async def screening_error_handler(
    request: Request, exc: screening_errors.ScreeningError
) -> JSONResponse:
    # 정의 파싱/스키마 다운그레이드/미지원 필터 등 입력 오류 — 400(EPIC-03).
    return JSONResponse(status_code=400, content=_detail(exc))


def register_error_handlers(app: FastAPI) -> None:
    # 구체적 예외를 먼저 등록해야 하위 클래스(UnknownFactorError/ParamValidationError 등)가
    # 상위 클래스(FactorError) 핸들러보다 우선 매칭된다.
    app.add_exception_handler(NotFoundError, not_found_handler)
    app.add_exception_handler(UnknownFactorError, unknown_factor_handler)
    app.add_exception_handler(ParamValidationError, param_validation_handler)
    app.add_exception_handler(FactorError, factor_error_handler)
    app.add_exception_handler(DefinitionError, definition_error_handler)
    app.add_exception_handler(WorkspaceError, workspace_error_handler)
    app.add_exception_handler(screening_errors.EmptyUniverseError, screening_empty_universe_handler)
    # MalformedDefinitionError/SchemaVersionError/UnsupportedFilterError는 별도 등록 없이도
    # MRO를 통해 아래 ScreeningError 핸들러로 위임된다(동일 핸들러이므로 중복 등록 불필요).
    app.add_exception_handler(screening_errors.ScreeningError, screening_error_handler)
