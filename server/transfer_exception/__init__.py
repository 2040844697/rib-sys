try:
    from .transfer_exception_module import TransferExceptionModule
except ImportError as exc:
    if "attempted relative import beyond top-level package" not in str(exc):
        raise
    __all__ = []
else:
    __all__ = ["TransferExceptionModule"]
