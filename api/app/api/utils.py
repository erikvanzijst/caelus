import logging

from starlette.requests import Request
from starlette.responses import JSONResponse

from app.services.errors import (
    CaelusException,
    DeploymentInProgressException,
    IntegrityException,
    NotFoundException,
)

ERROR_STATUS = {
    IntegrityException: 409,
    DeploymentInProgressException: 409,
    NotFoundException: 404
}

logger = logging.getLogger(__name__)


def _exception_handler(request: Request, exc: Exception):
    status = ERROR_STATUS.get(type(exc), 500)
    if status >= 500:
        logger.exception("Unhandled application error for path=%s: %s", request.url.path, exc)
    else:
        logger.warning("Request failed path=%s status=%s error=%s", request.url.path, status, exc)
    return JSONResponse({"detail": str(exc)}, status_code=status)


def register_exception_handlers(app):
    app.exception_handler(CaelusException)(_exception_handler)
    # app.exception_handler(ValidationError)(_exception_handler)
