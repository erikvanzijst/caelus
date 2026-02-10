class CaelusException(Exception):
    pass


class IntegrityException(CaelusException):
    pass


class NotFoundException(CaelusException):
    # Alias for compatibility with older code
    pass


# Backward‑compatible alias expected by the CLI tests
NotFoundError = NotFoundException
