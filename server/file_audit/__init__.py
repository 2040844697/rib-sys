try:
    from .audit_logs import DatabaseAuditService
    from .file_objects import DatabaseFileService
except ImportError as exc:
    if "attempted relative import beyond top-level package" not in str(exc):
        raise
    __all__ = []
else:
    __all__ = [
        "DatabaseAuditService",
        "DatabaseFileService",
    ]
