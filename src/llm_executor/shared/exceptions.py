"""Exception types for the LLM-Driven Secure Python Execution Platform."""


class ValidationError(Exception):
    """Base exception for validation errors."""

    def __init__(self, message: str, code: str = "", errors: list = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.errors = errors or []

    def to_dict(self):
        """Convert exception to dictionary."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "code": self.code,
            "errors": self.errors,
        }


class RestrictedOperationError(ValidationError):
    """Exception raised when code contains restricted operations."""

    def __init__(self, operation: str, code: str = ""):
        message = f"Restricted operation detected: {operation}"
        super().__init__(message, code, [message])
        self.operation = operation


class UnauthorizedImportError(ValidationError):
    """Exception raised when code contains unauthorized imports."""

    def __init__(self, imports: list, code: str = ""):
        message = f"Unauthorized imports detected: {', '.join(imports)}"
        super().__init__(message, code, [message])
        self.imports = imports


class MaxRetriesExceededError(ValidationError):
    """Exception raised when maximum validation retries are exceeded."""

    def __init__(self, attempts: int, code: str = ""):
        message = f"Maximum validation retries exceeded after {attempts} attempts"
        super().__init__(message, code, [message])
        self.attempts = attempts


class ExecutionError(Exception):
    """Base exception for execution errors."""

    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.retryable = retryable


class TimeoutError(ExecutionError):
    """Exception raised when execution exceeds timeout."""

    def __init__(self, timeout: int):
        message = f"Execution exceeded timeout of {timeout} seconds"
        super().__init__(message, retryable=False)
        self.timeout = timeout


class MemoryError(ExecutionError):
    """Exception raised when execution exceeds memory limit."""

    def __init__(self, limit: str):
        message = f"Execution exceeded memory limit of {limit}"
        super().__init__(message, retryable=False)
        self.limit = limit


class NetworkError(ExecutionError):
    """Exception raised when network operation is attempted."""

    def __init__(self):
        message = "Network operations are not allowed"
        super().__init__(message, retryable=False)


class ResourceExhaustedError(ExecutionError):
    """Exception raised when system resources are unavailable."""

    def __init__(self, resource: str):
        message = f"System resource exhausted: {resource}"
        super().__init__(message, retryable=True)
        self.resource = resource


class JobError(Exception):
    """Base exception for Kubernetes Job errors."""

    def __init__(self, message: str, job_id: str = ""):
        super().__init__(message)
        self.message = message
        self.job_id = job_id


class JobCreationError(JobError):
    """Exception raised when Kubernetes Job creation fails."""

    pass


class PodFailureError(JobError):
    """Exception raised when pod crashes or is evicted."""

    pass


class ImagePullError(JobError):
    """Exception raised when container image is unavailable."""

    pass


class DeadlineExceededError(JobError):
    """Exception raised when job exceeds activeDeadlineSeconds."""

    pass


class EventHubError(Exception):
    """Base exception for Event Hub errors."""

    def __init__(self, message: str, message_id: str = ""):
        super().__init__(message)
        self.message = message
        self.message_id = message_id


class MessageParsingError(EventHubError):
    """Exception raised when Event Hub message format is invalid."""

    pass


class ProcessingError(EventHubError):
    """Exception raised during Event Hub message handling."""

    pass


class PublishError(EventHubError):
    """Exception raised when publishing to Event Hub fails."""

    pass
