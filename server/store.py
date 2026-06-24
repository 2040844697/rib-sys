from __future__ import annotations

# 兼容旧测试和迁移中的导入。新代码应通过 app_context 装配服务，不再直接依赖 Store。
from .legacy_json_store import (
    Store,
    create_initial_data,
    create_seed_user,
    create_store,
    has_permission,
    hash_password,
    list_capabilities,
    normalize_text,
    verify_password,
)

__all__ = [
    "Store",
    "create_initial_data",
    "create_seed_user",
    "create_store",
    "has_permission",
    "hash_password",
    "list_capabilities",
    "normalize_text",
    "verify_password",
]
