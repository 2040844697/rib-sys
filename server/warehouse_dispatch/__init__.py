try:
    from .warehouse_dispatch_module import WarehouseDispatchModule
    from .warehouse_dispatch_repo import WarehouseDispatchRepository
except ImportError as exc:
    if "attempted relative import beyond top-level package" not in str(exc):
        raise
    __all__ = []
else:
    __all__ = ["WarehouseDispatchModule", "WarehouseDispatchRepository"]
