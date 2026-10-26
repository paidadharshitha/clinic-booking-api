"""Domain errors are independent of FastAPI and HTTP response construction."""


class DomainError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def not_found(resource: str) -> DomainError:
    return DomainError(404, f"{resource.upper()}_NOT_FOUND", f"{resource.capitalize()} not found.")
