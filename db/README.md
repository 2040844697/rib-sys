# Database Init

这套 SQL 用于把 RibSys 第一版核心业务表先建起来，包含：

- 用户与权限
- 商品图鉴 `goods` / `goods_images`
- 拼团 / 拼团商品 / 拼单记录
- 费用与付款
- 国际转运
- 国内囤货与排发
- 转单
- 文件对象
- 审计日志

当前 Python 后端仍然主要读写本地 JSON 文件，[server/.data/dev-db.json](/C:/Users/n2040/Documents/Ribsys/server/.data/dev-db.json)，还没有切到 PostgreSQL 作为正式存储。

## 初始化

1. 安装依赖：`pip install -r requirements.txt`
2. 准备 `.env`
3. 启动服务，服务会在启动时自动检查并执行 [db/init.sql](/C:/Users/n2040/Documents/Ribsys/db/init.sql)

启动检查逻辑：

- 如果 `DATABASE_URL` 未配置，则跳过
- 如果目标数据库不存在，则先自动创建数据库
- 如果 schema SQL 的 checksum 没变化，则跳过
- 如果 schema SQL 有变化，则重新执行整份初始化 SQL

服务会把已应用的 checksum 记录在数据库表 `ribsys_schema_bootstrap` 中。

如果本机有 `psql`，可以这样跑：

```bash
psql "$DATABASE_URL" -f db/init.sql
```

## 当前建议先落的表

- `groups`
- `users`
- `user_roles`
- `user_aliases`
- `file_objects`
- `goods`
- `goods_images`
- `payment_channels`
- `group_buys`
- `group_buy_items`
- `group_buy_records`
- `charges`
- `payment_proofs`
- `payment_proof_allocations`
- `price_adjustments`
- `audit_logs`

其余表也已经在 SQL 里建好了，方便后续模块继续接。
