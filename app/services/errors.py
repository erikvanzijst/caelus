class CaelusException(Exception):
    pass

class IntegrityException(CaelusException):
    pass

class NotFoundException(CaelusException):
    pass
