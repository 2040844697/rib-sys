class AppError(Exception):
    def __init__(self, status, message, code="APP_ERROR", details=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.details = details
