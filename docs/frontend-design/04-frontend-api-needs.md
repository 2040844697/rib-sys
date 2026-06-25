# 前端接口需求

本文档定义前端第一版页面需要的后端接口形状。这里的接口偏页面聚合 DTO，不等同于后端领域服务接口。

## 设计原则

- 页面尽量通过少量接口完成首屏渲染。
- 接口直接返回前端需要展示的状态和能力，不让前端重复拼复杂业务规则。
- 角色差异通过 `capabilities` 返回，前端根据能力展示按钮。
- 拼单记录展示状态由后端返回，前端不自行计算优先级。

## 登录与启动

### `POST /api/auth/login`

用途：

- 登录。

请求：

```json
{
  "account": "123456",
  "password": "password"
}
```

返回：

```json
{
  "userId": "user_1",
  "displayName": "成员A",
  "roles": ["member"],
  "next": "/app/groups"
}
```

### `POST /api/auth/logout`

用途：

- 退出登录。

返回：

```json
{
  "ok": true
}
```

### `GET /api/app/bootstrap`

用途：

- App 启动时获取当前用户、角色、默认群组和能力。

返回：

```json
{
  "currentUser": {
    "id": "user_1",
    "displayName": "成员A",
    "qqNumber": "123456",
    "groupNickname": "A昵称",
    "roles": ["member"]
  },
  "defaultGroupId": "group_1",
  "capabilities": [
    "group:view",
    "group_buy:view",
    "record:create_self"
  ]
}
```

## 谷团

### `GET /api/app/groups`

用途：

- 获取当前用户可见谷团列表。

返回：

```json
{
  "items": [
    {
      "id": "group_1",
      "name": "谷团",
      "coverImageUrl": null,
      "memberCount": 12,
      "activeGroupBuyCount": 1,
      "myRoles": ["member", "group_buy_maintainer"]
    }
  ]
}
```

### `GET /api/app/groups/{groupId}/home`

用途：

- 谷团详情首屏聚合接口。

返回：

```json
{
  "group": {
    "id": "group_1",
    "name": "谷团",
    "description": "团说明",
    "coverImageUrl": null,
    "leader": {
      "id": "user_owner",
      "displayName": "团长"
    },
    "memberCount": 12,
    "myRoles": ["member"]
  },
  "capabilities": {
    "canEditGroup": false,
    "canEnterAdmin": false,
    "canCreateGroupBuy": false
  },
  "summary": {
    "activeGroupBuyCount": 1,
    "myPendingPaymentCount": 2,
    "myDispatchableCount": 0
  }
}
```

### `GET /api/app/groups/{groupId}/group-buys`

用途：

- 获取谷团内拼团列表。

查询参数：

- `status`
- `keyword`
- `type`
- `page`
- `pageSize`

返回：

```json
{
  "items": [
    {
      "id": "gb_1",
      "title": "某系列开谷",
      "type": "群内开谷",
      "status": "拼拼拼",
      "initiator": {
        "id": "user_owner",
        "displayName": "团长"
      },
      "closeAt": "2026-06-30T12:00:00+08:00",
      "itemCount": 3,
      "availableQuantity": 12,
      "myRecordCount": 1,
      "coverImageUrl": null
    }
  ],
  "total": 1
}
```

### `GET /api/app/groups/{groupId}/admin-capabilities`

用途：

- 获取管理台入口可展示的功能。

返回：

```json
{
  "modules": [
    {
      "key": "group_buys",
      "title": "拼团管理",
      "description": "新建、编辑和查看拼团",
      "enabled": true
    },
    {
      "key": "warehouse",
      "title": "囤货排发",
      "description": "入库、排发和国内快递",
      "enabled": false
    }
  ]
}
```

## 拼团

### `GET /api/app/group-buys/{groupBuyId}/detail`

用途：

- 拼团详情首屏聚合接口。

返回：

```json
{
  "groupBuy": {
    "id": "gb_1",
    "groupId": "group_1",
    "title": "某系列开谷",
    "type": "群内开谷",
    "status": "拼拼拼",
    "description": "拼团说明",
    "closeAt": "2026-06-30T12:00:00+08:00"
  },
  "items": [
    {
      "id": "gbi_1",
      "name": "商品A",
      "alias": "A简称",
      "characterNames": ["角色A", "角色B"],
      "imageUrl": null,
      "unitPriceCny": "35.00",
      "totalQuantity": 20,
      "claimedQuantity": 8,
      "availableQuantity": 12,
      "status": "可拼"
    }
  ],
  "myRecords": [
    {
      "id": "record_1",
      "groupBuyItemId": "gbi_1",
      "quantity": 1,
      "displayStatus": "未肾",
      "isException": false
    }
  ],
  "capabilities": {
    "canClaim": true,
    "canEdit": false,
    "canUploadOrderScreenshot": false,
    "canManageRecords": false
  }
}
```

### `POST /api/group-buy-records`

用途：

- 成员认领拼单商品。

请求：

```json
{
  "groupBuyId": "gb_1",
  "groupBuyItemId": "gbi_1",
  "quantity": 1
}
```

返回：

```json
{
  "recordId": "record_1",
  "displayStatus": "未肾"
}
```

## 我的

### `GET /api/me`

用途：

- 获取个人信息。

返回：

```json
{
  "id": "user_1",
  "displayName": "成员A",
  "qqNumber": "123456",
  "groupNickname": "A昵称",
  "roles": ["member"]
}
```

### `PATCH /api/me`

用途：

- 更新个人信息。

请求：

```json
{
  "displayName": "成员A",
  "groupNickname": "A新昵称"
}
```

返回：

```json
{
  "ok": true
}
```
