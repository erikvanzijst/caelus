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


class HostnameException(CaelusException):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


# Backward‑compatible alias expected by the CLI tests
NotFoundError = NotFoundException
