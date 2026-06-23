# RibSys Backend Dev Server

这是一套为了第一阶段前端联调准备的 Python 后端。

## 目标

- 先接通前端已经在用的接口
- 支持登录、注册、会话、聚合查询和基础写操作
- 首次启动自动写入种子数据，并默认创建管理员账号
- 不依赖额外安装数据库或 Web 框架

## 启动

1. 启动后端：`pnpm server:dev`
2. 启动前端：`pnpm dev`
3. 如果想继续使用 MSW：`pnpm dev:mock`

如果你在 IDE 里直接运行，推荐启动模块 `server.app`。

## 首次启动数据

首次启动会在 [server/.data/dev-db.json](/C:/Users/n2040/Documents/Ribsys/server/.data/dev-db.json) 写入种子数据。

默认种子账号：

- `member` / `123456`
- `maintainer` / `123456`
- `stock` / `123456`
- `admin` / `123456`

其中 `admin` 是默认管理员账号；如果你通过环境变量覆盖了管理员账号或密码，以你的环境变量为准。

## 可选环境变量

- `RIBSYS_API_HOST`
- `RIBSYS_API_PORT`
- `RIBSYS_API_DATA_FILE`
- `RIBSYS_SEED_PASSWORD`
- `RIBSYS_ADMIN_ACCOUNT`
- `RIBSYS_ADMIN_PASSWORD`
- `RIBSYS_SESSION_TTL_MS`

## 当前已实现接口

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

## 文件与审计模块

当前已经独立实现了基础文件/审计模块，适合作为后续业务模块的通用依赖。

已提供能力：

- 文件对象登记
- 文件对象逻辑作废
- 审计日志统一写入
- 审计日志分页查询
- 旧 JSON 状态自动补齐 `fileObjects` 和对应计数器

说明：

- 文件对象目前仍使用本地 JSON 持久化，只登记元数据，不直接操作 MinIO。
- 审计快照会自动裁剪超长字符串、过深层级和过大集合，避免日志膨胀。
- 其他模块接入时建议只调用 `Store.file_service` / `Store.audit_service`，不要自行拼装审计记录。

## 说明

这版持久化使用本地 JSON 文件，适合当前的产品和接口联调阶段。后面如果我们开始补更完整的领域模型、审计查询、状态流转和多人协作，再把它替换成正式数据库会比较顺手。

## 数据库进度

PostgreSQL 初始化 SQL 已经补在 [db/init.sql](/C:/Users/n2040/Documents/Ribsys/db/init.sql)，其中包含商品图鉴相关表 `goods` 和 `goods_images`。

服务启动时会在检测到 `DATABASE_URL` 后自动执行数据库 schema 检查；如果目标数据库不存在，会先尝试自动创建数据库，再执行 [db/init.sql](/C:/Users/n2040/Documents/Ribsys/db/init.sql)。

当前服务本身还没有切到 PostgreSQL 读写，业务数据仍然使用本地 JSON 文件做联调数据源。
