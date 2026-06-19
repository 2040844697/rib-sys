# 关键接口草案

本文档只定义业务接口形状，不限定具体技术栈。

## 通用约定

- 金额单位为 CNY，建议后端以分为最小单位存储
- 重量单位为 gram
- 所有关键修改接口都应写入审计日志
- 系统只记录线下付款，不接入支付网关
- 拼单状态第一版使用中文业务状态：等待开团、拼拼拼、已切、已截团、已完成、已取消
- 图片字段保存对象 URL，第一版对象来源为本地 MinIO 服务

## 用户与身份

### 获取当前用户

GET /api/me

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

### 管理员更新用户身份

PATCH /api/users/{userId}

请求：

```json
{
  "displayName": "成员A",
  "qqNumber": "123456",
  "groupNickname": "A新昵称",
  "roles": ["member", "warehouse"]
}
```

## 拼单

### 创建拼单

POST /api/group-buys

请求：

```json
{
  "groupId": "group_1",
  "title": "某系列 goods 拼团",
  "description": "拼团说明",
  "closeAt": "2026-06-30T12:00:00+08:00",
  "paymentChannelId": "pay_1",
  "products": [
    {
      "name": "商品A",
      "priceCny": "35.00",
      "estimatedWeightGram": 80,
      "quantityLimit": 20,
      "reservations": [
        {
          "reservedForUserId": "user_owner",
          "quantity": 1,
          "reason": "拼主自留"
        }
      ]
    }
  ]
}
```

### 参与拼单

POST /api/group-buys/{groupBuyId}/participations

请求：

```json
{
  "items": [
    {
      "productId": "product_1",
      "quantity": 2
    },
    {
      "productId": "product_2",
      "quantity": 1
    }
  ]
}
```

行为：

- 创建或更新参团记录
- 按本次拼单合并生成首款费用

### 更新拼单状态

POST /api/group-buys/{groupBuyId}/status

请求：

```json
{
  "status": "已切",
  "reason": "已切，继续拼出剩余库存"
}
```

### 申请调价

POST /api/group-buys/{groupBuyId}/price-adjustments

请求：

```json
{
  "productId": "product_1",
  "newPriceCny": "32.00",
  "reason": "已切后降价拼出剩余库存"
}
```

行为：

- 如果尚未生成应收或付款，可直接更新后续价格并记录审计
- 如果已有应收或付款，创建待审核调价申请
- 审核通过后，对已受影响成员生成补款或退款记录

## 费用与付款记录

### 查询我的费用

GET /api/my/charges

可筛选：

- status
- type
- groupBuyId

### 上传付款记录

POST /api/charges/{chargeId}/payment-proofs

请求：

```json
{
  "amountCny": "105.00",
  "paidAt": "2026-06-19T20:00:00+08:00",
  "proofImageUrl": "http://minio.local/ribsys/proofs/proof.jpg",
  "note": "支付宝已付"
}
```

### 确认付款记录

POST /api/payment-proofs/{proofId}/confirm

请求：

```json
{
  "note": "金额已核对"
}
```

### 驳回付款记录

POST /api/payment-proofs/{proofId}/reject

请求：

```json
{
  "reason": "截图金额不清晰"
}
```

## 日本订单

### 创建日本订单

POST /api/group-buys/{groupBuyId}/japan-orders

请求：

```json
{
  "buyerUserId": "user_2",
  "orderScreenshotUrl": "http://minio.local/ribsys/orders/order.jpg",
  "website": null,
  "websiteOrderNo": null,
  "orderedAt": "2026-06-20T10:00:00+09:00",
  "items": [
    {
      "participationItemId": "pi_1",
      "quantity": 2
    }
  ]
}
```

### 更新日本订单状态

POST /api/japan-orders/{japanOrderId}/status

请求：

```json
{
  "status": "arrived_forwarder",
  "reason": "已入日本转运仓"
}
```

## 国际转运批次

### 创建批次

POST /api/international-batches

请求：

```json
{
  "forwarderName": "某转运",
  "batchNo": "BATCH-001",
  "warehouseUserId": "user_warehouse",
  "japanOrderIds": ["jo_1", "jo_2"]
}
```

### 录入批次费用并生成分摊

POST /api/international-batches/{batchId}/fee-allocations

请求：

```json
{
  "totalWeightGram": 3200,
  "shippingFeeCny": "420.00",
  "taxFeeCny": "80.00",
  "otherFeeCny": "0.00",
  "taxAllocationMode": "equal_by_user",
  "shippingAllocationMode": "by_weight",
  "manualAdjustments": [
    {
      "userId": "user_1",
      "adjustmentCny": "2.00",
      "note": "重量修正"
    }
  ]
}
```

行为：

- 生成 InternationalFeeAllocation
- 为每个成员生成国际费用 Charge
- 税费默认按本次国际运输涉及的全部订单成员均摊，具体金额允许手动编辑

## 囤货与排发

### 确认国内入库

POST /api/international-batches/{batchId}/stock-in

请求：

```json
{
  "stockedAt": "2026-07-05T18:00:00+08:00",
  "note": "已清点"
}
```

行为：

- 生成或更新 StockItem
- 对应成员商品进入 dispatchable 状态

### 查询我的可排发商品

GET /api/my/dispatchable-items

### 创建排发申请

POST /api/dispatch-requests

请求：

```json
{
  "warehouseUserId": "user_warehouse",
  "items": [
    {
      "stockItemId": "stock_1",
      "quantity": 1
    }
  ],
  "receiverName": "张三",
  "receiverPhone": "13800000000",
  "receiverAddress": "国内地址",
  "note": "可以塞防水袋"
}
```

### 录入国内运费

POST /api/dispatch-requests/{dispatchRequestId}/domestic-fee

请求：

```json
{
  "shippingFeeCny": "12.00",
  "feeMode": "prepaid",
  "paymentChannelId": "pay_warehouse",
  "note": "中通"
}
```

行为：

- prepaid 生成国内运费 Charge
- cod 不生成待确认 Charge，仅记录到付

### 录入国内快递

POST /api/dispatch-requests/{dispatchRequestId}/shipment

请求：

```json
{
  "carrier": "中通",
  "trackingNo": "ZT123",
  "shippedAt": "2026-07-08T12:00:00+08:00"
}
```

## 转单

### 申请转单

POST /api/transfers

请求：

```json
{
  "toUserId": "user_2",
  "items": [
    {
      "participationItemId": "pi_1",
      "quantity": 1
    }
  ],
  "reason": "群内转单"
}
```

### 确认转单

POST /api/transfers/{transferId}/approve

请求：

```json
{
  "note": "双方已确认"
}
```

行为：

- 原成员对应份额减少或转出
- 新成员获得对应份额
- 后续未发生费用归新成员
- 历史已确认付款记录不迁移，只保留追溯关系
- 转单默认要求双方线下确认后提交申请，再由维护人或管理员审核通过
