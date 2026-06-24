# JSON Legacy Runtime Removed

## Current State

The backend no longer supports the old JSON/state runtime. `AppContext` is the only composition root for HTTP routes, and it wires database-backed modules directly.

Removed legacy pieces:

- the compatibility wrapper for the old application container
- the JSON-backed application container implementation
- local development JSON data under the backend data directory
- unit tests that depended on the removed container, seed-data factory, or persistent module dictionaries

## Runtime Rules

- `DATABASE_URL` is required at startup.
- Authentication, sessions, profile updates, file objects, audit logs, and business modules use database-backed services.
- Code must not add fallback logic to a JSON runtime.
- Missing DB module wiring should fail explicitly with `RuntimeError("DB implementation required.")` or a module-specific database-required error.

## Compatibility Boundary

The API may still return a boolean startup/health field indicating that the legacy JSON runtime is disabled, but the value must remain false. That field is response metadata only; it is not permission to reintroduce the JSON store.
