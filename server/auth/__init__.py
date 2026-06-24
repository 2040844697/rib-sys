try:
    from .bootstrap import ensure_identity_seed
    from .auth_module import AuthModule
    from .permissions import has_permission, has_role, list_capabilities
    from .repository import AuthRepository
    from .security import hash_password, normalize_text, verify_password
    from .sessions import SessionRepository
except ImportError as exc:
    if "attempted relative import beyond top-level package" not in str(exc):
        raise
    __all__ = []
else:
    __all__ = [
        "AuthModule",
        "AuthRepository",
        "SessionRepository",
        "ensure_identity_seed",
        "has_permission",
        "has_role",
        "hash_password",
        "list_capabilities",
        "normalize_text",
        "verify_password",
    ]
