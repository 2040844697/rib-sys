# RibSys Backend Dev Server

This Python backend runs against PostgreSQL only. The legacy JSON/state runtime has been removed.

## Startup

1. Configure `DATABASE_URL`.
2. Start the backend: `pnpm server:dev`
3. Start the frontend: `pnpm dev`
4. Use `pnpm dev:mock` only when you intentionally want the frontend MSW mock layer.

When running directly from an IDE, start the module `server.app`.

## Seed Data

On startup, the backend checks the database schema and seeds the default identity data when needed.

Default seed accounts:

- `member` / `123456`
- `maintainer` / `123456`
- `stock` / `123456`
- `admin` / `123456`

`admin` is the default administrator account. `RIBSYS_ADMIN_ACCOUNT`, `RIBSYS_ADMIN_PASSWORD`, and `RIBSYS_SEED_PASSWORD` can override the defaults.

## Environment Variables

- `DATABASE_URL`
- `RIBSYS_API_HOST`
- `RIBSYS_API_PORT`
- `RIBSYS_SEED_PASSWORD`
- `RIBSYS_ADMIN_ACCOUNT`
- `RIBSYS_ADMIN_PASSWORD`
- `RIBSYS_SESSION_TTL_MS`
- `RIBSYS_DB_INIT_SQL_FILE`
- `RIBSYS_DB_BOOTSTRAP_ADMIN_DB`
- `RIBSYS_INIT_DB_ON_STARTUP`
- `MINIO_ENDPOINT`
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`

## Implemented API Surface

- `POST /api/auth/login`
- `POST /api/auth/register`
- `POST /api/auth/logout`
- `GET /api/app/bootstrap`
- `GET /api/app/groups`
- `GET /api/app/groups/:groupId/home`
- `GET /api/app/groups/:groupId/group-buys`
- `GET /api/app/groups/:groupId/admin-capabilities`
- `GET /api/app/group-buys/:groupBuyId/detail`
- `POST /api/group-buy-records`
- `POST /api/group-buys`
- `POST /api/file-objects`
- `POST /api/file-objects/:fileObjectId/void`
- `GET /api/audit-logs`
- `GET /api/me`
- `PATCH /api/me`
- `GET /api/health`

## Database

Schema initialization lives in [db/init.sql](/C:/Users/n2040/Documents/Ribsys/db/init.sql). Startup runs the schema bootstrap when `RIBSYS_INIT_DB_ON_STARTUP` is enabled.
