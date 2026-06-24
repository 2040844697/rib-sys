try:
    from .goods_catalog_module import GoodsCatalogModule
    from .goods_catalog_repo import GoodsCatalogRepository
except ImportError as exc:
    if "attempted relative import beyond top-level package" not in str(exc):
        raise
    __all__ = []
else:
    __all__ = ["GoodsCatalogModule", "GoodsCatalogRepository"]
