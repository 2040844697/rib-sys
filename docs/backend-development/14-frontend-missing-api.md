# 前端新页面接口补齐记录

本文档记录全新前端界面需要的接口，以及本轮在 `server` 中的实现状态。以下接口已补齐挂载；已有接口前端会直接使用，不在这里重复。

## 我的拼单和记录

`GET /api/app/me/records`

状态：已实现。

用途：

- 返回当前用户参与的拼团记录、商品份额、展示状态、关联费用、排发和转单状态。

## 拼团创建/编辑扩展字段

现有 `POST /api/group-buys`、`PATCH /api/group-buys/{groupBuyId}` 已用于新建拼团页，但当前后端只持久化 `groupId`、`type`、`title`、`description`、`closeAt`、`paymentChannelId`、`warehouseUserId`。

状态：已实现。

新建拼团页还需要后端支持以下字段：

- `startAt`：活动开始时间。
- `coverImageUrl` / `coverFileObjectId`：活动主图。
- `claimMode`：拼谷类型，例如 `拼盒`、`单领`。
- `canCancelClaim`：是否允许成员撤排。
- `saleMode`：售卖方式，例如 `全款`、`定金尾款`。
- `allowTransfer`：是否允许团员转单。
- `advancedSettings`：高级展示/提醒配置，包括 `remindBeforeStart`、`showParticipantCount`、`showTotalAmount`、`showClaimedQuantity`。

期望：详情接口 `GET /api/app/group-buys/{groupBuyId}/detail` 同步返回上述字段，便于编辑页回填。

`DELETE /api/group-buy-items/{groupBuyItemId}`

状态：已实现。

用途：

- 编辑拼团时删除尚未有人认领的谷子条目。
- 如果已有认领记录，应返回明确业务错误，并由前端提示不能直接删除。

`POST /api/group-buy-items`

状态：已实现。

新增入参：

- `initialRecords`：创建拼团商品时一并初始化的拼单记录列表，格式为 `{ memberUserId, quantity, note? }[]`。

规则：

- `initialRecords` 不是一张独立“自留/预留”业务表，只是创建时的便捷输入。
- 后端在同一事务中创建正常的 `group_buy_records`，并同步维护 `group_buy_items.claimed_quantity` 与 `available_quantity`。
- 每个成员同一商品只生成或合并为一条拼单记录。
- 这些记录后续进入普通“我的拼单/费用/排发/转单”流程。

`GET /api/app/groups/{groupId}/members`

状态：已实现。

用途：

- 新建拼团页的初始化拼单记录归属人搜索。
- 支持 `keyword`、`pageSize`。
- 普通成员只能查到自己；拼单维护人和管理员可搜索当前谷团成员。

## 文件上传

`POST /api/file-uploads`

状态：已实现。

用途：

- 浏览器直接上传图片文件，返回 `fileObjectId`、`url`、`bucket`。
- 新建拼团页需要用于活动主图和手动新增谷子图片。

说明：接口支持 `multipart/form-data` 的 `file` 字段，也兼容 JSON 登记路径。开发环境文件保存到 `public/uploads/{bucket}/...`，并登记到 `file_objects`。

## 我的费用

`GET /api/my/charges`

状态：已实现。

用途：

- 返回当前用户的首款、国际费、国内运费、补款和退款费用列表。

`POST /api/charges/{chargeId}/payment-proofs`

状态：已实现。

用途：

- 当前用户为指定费用上传付款凭证。

## 收款方式

`GET /api/payment-channels`

状态：已实现。

用途：

- 返回当前用户可用的收款方式列表。

`POST /api/payment-channels`

状态：已实现。

用途：

- 新建收款方式。

## 可排发和排发申请

`GET /api/my/dispatchable-items`

状态：已实现。

用途：

- 返回当前用户所有可排发商品，包含 `stockItemId`、拼团、商品、数量、囤货人。

`POST /api/dispatch-requests`

状态：已实现。

用途：

- 创建排发申请。

`GET /api/dispatch-requests`

状态：已实现。

用途：

- 囤货人查看待处理排发申请列表。

## 转单

`GET /api/transfers`

状态：已实现。

用途：

- 管理员或维护人查看转单申请列表。

`POST /api/transfers`

状态：已实现。

用途：

- 成员基于自己记录发起转单申请。

`POST /api/transfers/{transferId}/approve`

状态：已实现。

用途：

- 审核通过转单。

`POST /api/transfers/{transferId}/reject`

状态：已实现。

用途：

- 审核驳回转单。

## 异常处理

`GET /api/exceptions`

状态：已实现。

用途：

- 管理员查看待处理异常列表。

## 用户与角色

`GET /api/users`

状态：已实现。

用途：

- 管理员查看用户列表。

`PATCH /api/users/{userId}`

状态：已实现。

用途：

- 管理员更新用户展示名、QQ、群昵称、角色和状态。

## 地址簿

`GET /api/me/addresses`

状态：已实现。

用途：

- 当前用户查看常用地址。

`POST /api/me/addresses`

状态：已实现。

用途：

- 新增常用地址。
