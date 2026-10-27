class ServiceError(Exception):
    """Base error for AI/media services. `code` is stable and shown to admins."""
    code = "SERVICE_ERROR"
    retryable = False

    def __init__(self, message: str, code: str | None = None, retryable: bool | None = None):
        super().__init__(message)
        if code:
            self.code = code
        if retryable is not None:
            self.retryable = retryable


class NotConfigured(ServiceError):
    """A provider, credential or dependency is missing. Message explains how to fix it."""
    code = "NOT_CONFIGURED"


class UploadError(ServiceError):
    code = "UPLOAD_INVALID"
