# 文件与审计模块说明

本文档描述当前已经落地的文件与审计模块实现，方便后续模块直接复用。

## 简介

文件与审计模块是一个基础支撑模块，当前主要负责两类能力：

- 文件对象元数据登记与逻辑作废
- 审计日志统一写入与分页查询

当前实现位于 [server/file_audit/audit_logs.py](/C:/Users/n2040/Documents/Ribsys/server/file_audit/audit_logs.py) 和 [server/file_audit/file_objects.py](/C:/Users/n2040/Documents/Ribsys/server/file_audit/file_objects.py)，并由 [server/app_context.py](/C:/Users/n2040/Documents/Ribsys/server/app_context.py) 统一装配。

应用使用数据库版 `DatabaseAuditService` / `DatabaseFileService`，直接读写 `audit_logs` 和 `file_objects` 表。`DATABASE_URL` 是启动必需配置；本地 JSON 兼容实现已经移除。

## 当前功能

### 1. 文件对象登记

用于登记一个已经上传完成的文件对象元数据。

当前记录字段包括：

- `id`
- `bucket`
- `objectKey`
- `url`
- `contentType`
- `sizeBytes`
- `uploadedBy`
- `status`
- `createdAt`
- `updatedAt`

对应数据库字段：

- `id`
- `bucket`
- `object_key`
- `url`
- `content_type`
- `size_bytes`
- `uploaded_by`
- `status`
- `created_at`
- `updated_at`

当前允许的 bucket：

- `goods`
- `payments`
- `orders`
- `channels`
- `misc`

规则：

- `bucket`、`objectKey`、`url` 必填
- `sizeBytes` 如传入，必须是大于等于 0 的整数
- 同一个 `bucket + objectKey` 不允许重复登记
- 当前只登记元数据，不直接上传或删除 MinIO 文件

### 2. 文件对象逻辑作废

用于把已登记文件标记为作废。

规则：

- 当前只做逻辑作废，不删除真实文件
- 作废后状态从 `active` 变为 `voided`
- 重复作废会报错
- 作废动作会自动写入审计日志

### 3. 审计日志统一写入

所有业务模块后续都应该通过统一入口写审计，不要自己拼接审计记录。

当前审计字段包括：

- `id`
- `actorUserId`
- `action`
- `objectType`
- `objectId`
- `before`
- `after`
- `reason`
- `createdAt`

说明：

- `actorUserId` 允许为 `system`
- `before` / `after` 支持任意 JSON 结构
- 审计写入后不提供普通修改能力

### 4. 审计快照裁剪

为避免审计日志体积膨胀，当前实现会自动裁剪快照内容。

当前策略：

- 超长字符串截断为最多 500 个字符
- 数组最多保留前 20 项
- 对象最多保留前 30 个字段
- 嵌套深度最多保留 4 层

超出部分会用 `...[truncated]` 或说明性占位文本表示。

### 5. 审计分页查询

当前支持按条件查询审计日志，并返回分页结果。

支持过滤字段：

- `objectType`
- `objectId`
- `actorUserId`
- `action`
- `createdFrom`
- `createdTo`
- `page`
- `pageSize`

规则：

- 默认 `page=1`
- 默认 `pageSize=20`
- 最大 `pageSize=100`
- 当前只有具备 `audit:view` 权限的用户可查询

## 模块边界

本模块负责：

- 文件对象元数据的校验、登记、作废
- 审计日志的写入、裁剪、查询
- 读写 `file_objects` / `audit_logs`

本模块暂不负责：

- MinIO 文件上传
- MinIO 文件存在性校验
- 业务对象归属判断
- 各业务模块的权限细分策略设计

## 对内服务接口

### `DatabaseFileService.create_upload_object(...)`

作用：

- 创建文件对象记录

参数：

- `uploaded_by`
- `bucket`
- `object_key`
- `url`
- `content_type`
- `size_bytes`

返回：

- `fileObjectId`
- `url`
- `fileObject`

### `DatabaseFileService.void_file_object(...)`

作用：

- 作废文件对象

参数：

- `actor_user_id`
- `file_object_id`
- `reason`

返回：

- `fileObjectId`
- `status`

### `DatabaseAuditService.log(...)`

作用：

- 写入审计日志

参数：

- `actor_user_id`
- `action`
- `object_type`
- `object_id`
- `before`
- `after`
- `reason`

返回：

- 完整审计记录对象

### `DatabaseAuditService.list_logs(...)`

作用：

- 查询审计日志

参数：

- `viewer`
- `filters`

返回：

- `items`
- `total`
- `page`
- `pageSize`

## 当前 HTTP 接口

### `POST /api/file-objects`

作用：

- 登记文件对象

请求体：

```json
{
  "bucket": "orders",
  "objectKey": "2026/06/demo.png",
  "url": "https://files.example.com/orders/2026/06/demo.png",
  "contentType": "image/png",
  "sizeBytes": 2048
}
```

响应示例：

```json
{
  "fileObjectId": "file_1",
  "url": "https://files.example.com/orders/2026/06/demo.png",
  "fileObject": {
    "id": "file_1",
    "bucket": "orders",
    "objectKey": "2026/06/demo.png",
    "url": "https://files.example.com/orders/2026/06/demo.png",
    "contentType": "image/png",
    "sizeBytes": 2048,
    "uploadedBy": "user_admin",
    "status": "active",
    "createdAt": "2026-06-20T12:00:00Z",
    "updatedAt": "2026-06-20T12:00:00Z"
  }
}
```

### `POST /api/file-objects/:fileObjectId/void`

作用：

- 作废文件对象

请求体：

```json
{
  "reason": "上传错文件"
}
```

响应示例：

```json
{
  "fileObjectId": "file_1",
  "status": "voided"
}
```

### `GET /api/audit-logs`

作用：

- 查询审计日志

查询参数：

- `object_type`
- `object_id`
- `actor_user_id`
- `action`
- `created_from`
- `created_to`
- `page`
- `page_size`

响应示例：

```json
{
  "items": [
    {
      "id": "audit_2",
      "actorUserId": "user_admin",
      "action": "file_object.void",
      "objectType": "file_object",
      "objectId": "file_1",
      "before": {
        "status": "active"
      },
      "after": {
        "status": "voided"
      },
      "reason": "上传错文件",
      "createdAt": "2026-06-20T12:05:00Z",
      "actorUser": {
        "id": "user_admin",
        "account": "admin",
        "displayName": "管理员莓莓",
        "qqNumber": "445566",
        "groupNickname": "莓莓",
        "roles": ["member", "group_buy_maintainer", "stock_keeper", "admin"]
      }
    }
  ],
  "total": 1,
  "page": 1,
  "pageSize": 20
}
```

## 存储说明

当前应用路径使用 PostgreSQL。

数据库表：

- `file_objects`
- `audit_logs`

旧本地 JSON 状态字段和启动补齐逻辑已经删除。

## 后续接入建议

后续其他模块如果需要上传截图、二维码、商品图或写关键操作审计，建议统一走这里：

- 文件类能力走 `AppContext.file_service`
- 审计类能力走 `AppContext.audit_service`

这样做的好处：

- 校验规则统一
- 审计格式统一
- 各业务模块不需要自行处理审计表和文件表细节
