from starlette.requests import Request
from starlette.responses import JSONResponse

from app.services.errors import CaelusException, IntegrityException, NotFoundException

ERROR_STATUS = {
    IntegrityException: 409,
    NotFoundException: 404
}

def _exception_handler(request: Request, exc: Exception):
    return JSONResponse({"detail": str(exc)}, status_code=ERROR_STATUS.get(type(exc), 500))


def register_exception_handlers(app):
    app.exception_handler(CaelusException)(_exception_handler)
