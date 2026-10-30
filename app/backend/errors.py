from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, error_code: str, message: str):
        self.status, self.error_code, self.message = status, error_code, message


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse({"error_code": exc.error_code, "message": exc.message}, status_code=exc.status)
