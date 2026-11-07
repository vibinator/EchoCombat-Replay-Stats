"""One error shape for the whole API: {"error_code", "message"} (api.ts shows `message`). ApiError is raised by the
handlers; FastAPI's own validation errors and integer overflows (Review BUG-4 / BUG-9) are translated to it too."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, error_code: str, message: str):
        self.status, self.error_code, self.message = status, error_code, message


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse({"error_code": exc.error_code, "message": exc.message}, status_code=exc.status)


def _where(loc) -> str:
    parts = [str(p) for p in loc if p not in ("query", "body", "path", "header")]
    return ".".join(parts) if parts else "request"


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 with a readable sentence: `limit: Input should be less than or equal to 200`. The field list is kept under
    `detail` for scripts that read it."""
    errors = exc.errors()
    first = errors[0] if errors else {}
    message = f"{_where(first.get('loc', ()))}: {first.get('msg', 'invalid value')}" if first else "Invalid request"
    return JSONResponse({"error_code": "bad_request", "message": message,
                         "detail": [{"loc": list(e.get("loc", ())), "msg": e.get("msg", "")} for e in errors]}, status_code=422)


async def overflow_error_handler(_request: Request, _exc: OverflowError) -> JSONResponse:
    """An id too large for SQLite (`/api/matches/99999999999999999999`): not found, not a 500."""
    return JSONResponse({"error_code": "not_found", "message": "Not found"}, status_code=404)
