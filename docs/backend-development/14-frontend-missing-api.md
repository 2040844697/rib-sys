# 前端新页面待补接口

本文档记录全新前端界面需要、但当前 `server/app.py` 尚未挂载的接口。已有接口前端会直接使用，不在这里重复。

## 我的拼单和记录

`GET /api/app/me/records`

用途：

- 返回当前用户参与的拼团记录、商品份额、展示状态、关联费用、排发和转单状态。

## 我的费用

`GET /api/my/charges`

用途：

- 返回当前用户的首款、国际费、国内运费、补款和退款费用列表。

`POST /api/charges/{chargeId}/payment-proofs`

用途：

- 当前用户为指定费用上传付款凭证。

## 收款方式

`GET /api/payment-channels`

用途：

- 返回当前用户可用的收款方式列表。

`POST /api/payment-channels`

用途：

- 新建收款方式。

## 可排发和排发申请

`GET /api/my/dispatchable-items`

用途：

- 返回当前用户所有可排发商品，包含 `stockItemId`、拼团、商品、数量、囤货人。

`POST /api/dispatch-requests`

用途：

- 创建排发申请。

`GET /api/dispatch-requests`

用途：

- 囤货人查看待处理排发申请列表。

## 转单

`GET /api/transfers`

用途：

- 管理员或维护人查看转单申请列表。

`POST /api/transfers`

用途：

- 成员基于自己记录发起转单申请。

`POST /api/transfers/{transferId}/approve`

用途：

- 审核通过转单。

`POST /api/transfers/{transferId}/reject`

用途：

- 审核驳回转单。

## 异常处理

`GET /api/exceptions`

用途：

- 管理员查看待处理异常列表。

## 用户与角色

`GET /api/users`

用途：

- 管理员查看用户列表。

`PATCH /api/users/{userId}`

用途：

- 管理员更新用户展示名、QQ、群昵称、角色和状态。

## 地址簿

`GET /api/me/addresses`

用途：

- 当前用户查看常用地址。

`POST /api/me/addresses`

用途：

- 新增常用地址。
