from __future__ import annotations

from typing import Any


ROLE_PERMISSIONS = {
    "member": [
        "group:view",
        "group_buy:view",
        "record:create_self",
        "record:view_self",
        "charge:view_self",
        "dispatch:create_self",
    ],
    "group_buy_maintainer": [
        "goods:create",
        "goods:update",
        "goods:view",
        "group_buy:create",
        "group_buy:update_own",
        "group_buy:update_any",
        "group_buy:cancel",
        "record:create_for_member",
        "record:view_group",
        "record:mark_exception",
        "charge:view_group",
        "charge:confirm_payment",
        "charge:adjust",
    ],
    "stock_keeper": [
        "dispatch:process_assigned",
        "warehouse:view",
        "goods:view",
        "charge:confirm_payment",
    ],
    "admin": [
        "group:edit",
        "member:manage",
        "audit:view",
        "user:manage",
        "role:manage",
    ],
}


def has_role(user: dict[str, Any], expected_roles: str | list[str]) -> bool:
    roles = expected_roles if isinstance(expected_roles, list) else [expected_roles]
    return any(role in user.get("roles", []) for role in roles)


def has_permission(user: dict[str, Any], permission: str) -> bool:
    roles = user.get("roles", [])
    if "admin" in roles:
        return True

    return any(permission in ROLE_PERMISSIONS.get(role, []) for role in roles)


def list_capabilities(user: dict[str, Any]) -> list[str]:
    roles = user.get("roles", [])
    capabilities = {"group:view", "group_buy:view", "record:create_self"}
    for role in roles:
        capabilities.update(ROLE_PERMISSIONS.get(role, []))
    if "admin" in roles:
        for role_permissions in ROLE_PERMISSIONS.values():
            capabilities.update(role_permissions)
    return sorted(capabilities)
