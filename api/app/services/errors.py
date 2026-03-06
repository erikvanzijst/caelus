class CaelusException(Exception):
    pass


class IntegrityException(CaelusException):
    pass


class DeploymentInProgressException(CaelusException):
    pass


class NotFoundException(CaelusException):
    # Alias for compatibility with older code
    pass


class ValidationException(CaelusException):
    pass


# Backward‑compatible alias expected by the CLI tests
NotFoundError = NotFoundException
