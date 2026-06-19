# 领域模型草案

## User 用户

字段：

- id
- display_name
- qq_number
- group_nickname
- group_id
- roles
- status
- created_at
- updated_at

说明：

- QQ 号和群昵称用于关联群内身份
- 群昵称可能变化，应允许维护历史别名

## Group 群

字段：

- id
- name
- qq_group_number
- description
- status

## GroupBuy 拼单

字段：

- id
- group_id
- title
- description
- status
- owner_user_id
- close_at
- payment_channel_id
- created_at
- updated_at

说明：

- 一个拼单可包含多个商品
- 拼单价格均为 CNY，不处理汇率
- status 需要支持“拼拼拼”和“已切”等业务展示状态

## Product 商品

字段：

- id
- group_buy_id
- name
- sku
- description
- image_url
- price_cny
- estimated_weight_gram
- quantity_limit
- status

说明：

- estimated_weight_gram 用于后续国际运费分摊
- 实际分摊时可以覆盖或调整重量

## ProductReservation 内定库存

字段：

- id
- group_buy_id
- product_id
- reserved_for_user_id
- quantity
- reason
- created_by
- created_at

说明：

- 用于记录拼主自留或提前沟通后为某个成员预留的库存
- 内定库存应生成对应成员的参团商品明细
- 如果后续取消内定，应写入审计记录

## Participation 参团记录

字段：

- id
- group_buy_id
- user_id
- status
- created_at

说明：

- 表示某个用户参与了某个拼单
- 同一拼单内一个用户通常只有一条参团记录

## ParticipationItem 参团商品明细

字段：

- id
- participation_id
- product_id
- quantity
- unit_price_cny
- subtotal_cny
- status

说明：

- unit_price_cny 记录参团时价格，避免后续商品价格调整影响历史
- 转单、取消、缺货都应体现在明细状态或后续调整记录中

## PriceAdjustment 调价申请

字段：

- id
- group_buy_id
- product_id
- old_price_cny
- new_price_cny
- reason
- status
- requested_by
- reviewed_by
- reviewed_at
- created_at

说明：

- 调价发生在已有付款或已生成应收之后时，需要审核
- 审核通过后，不覆盖历史参团价格，而是生成补款或退款费用
- 未付款的新参团记录可以按新价格生成应收

## PaymentChannel 收款渠道

字段：

- id
- owner_user_id
- type
- display_name
- qr_image_url
- account_text
- note
- status

说明：

- 用于展示拼单维护人、下单人或囤货人的收款二维码和说明
- 系统只展示和记录，不实际收款

## Charge 费用/肾

字段：

- id
- type
- payer_user_id
- payee_user_id
- related_object_type
- related_object_id
- amount_cny
- status
- due_at
- note
- created_by
- confirmed_by
- confirmed_at

说明：

- type 表示首款、国际费用、国内运费、补款、退款等
- related_object 可指向拼单、国际转运批次、排发申请等
- 首款通常按用户和拼单合并生成一条 Charge

## PaymentProof 付款记录

字段：

- id
- charge_id
- submitted_by
- amount_cny
- paid_at
- proof_image_url
- note
- status
- reviewed_by
- reviewed_at
- reject_reason

## JapanOrder 日本网站订单

字段：

- id
- group_buy_id
- buyer_user_id
- website
- website_order_no
- order_screenshot_url
- status
- ordered_at
- shipped_at
- arrived_forwarder_at
- note

说明：

- 一个拼单可对应多个日本网站订单
- 一个日本网站订单也可包含同一拼单内多个商品
- 下单截图是主要凭证
- website 和 website_order_no 可以为空

## JapanOrderItem 日本订单明细

字段：

- id
- japan_order_id
- participation_item_id
- quantity
- status

说明：

- 用于追踪具体成员商品份额进入了哪个日本订单

## InternationalBatch 国际转运批次

字段：

- id
- forwarder_name
- batch_no
- status
- warehouse_user_id
- international_tracking_no
- total_weight_gram
- shipping_fee_cny
- tax_fee_cny
- other_fee_cny
- shipped_at
- arrived_domestic_at
- stocked_at
- note

## InternationalBatchOrder 批次订单关联

字段：

- id
- batch_id
- japan_order_id

## InternationalFeeAllocation 国际费用分摊

字段：

- id
- batch_id
- user_id
- weight_gram
- shipping_fee_cny
- tax_fee_cny
- other_fee_cny
- adjustment_cny
- total_cny
- note

说明：

- 运费默认按重量分摊
- 税费默认按人均摊
- 最终金额允许人工调整并记录原因

## StockItem 国内囤货商品

字段：

- id
- warehouse_user_id
- participation_item_id
- quantity
- status
- stocked_at

说明：

- 到国内囤货后生成或更新
- 可被排发申请选择

## DispatchRequest 排发申请

字段：

- id
- requester_user_id
- warehouse_user_id
- status
- receiver_name
- receiver_phone
- receiver_address
- note
- submitted_at
- packed_at
- shipped_at
- completed_at

## DispatchItem 排发明细

字段：

- id
- dispatch_request_id
- stock_item_id
- quantity

## DomesticShipment 国内快递

字段：

- id
- dispatch_request_id
- carrier
- tracking_no
- shipping_fee_cny
- fee_mode
- shipped_at
- note

fee_mode：

- prepaid：先付
- cod：到付
- waived：无需付款

## Transfer 转单

字段：

- id
- from_user_id
- to_user_id
- status
- reason
- requested_by
- approved_by
- approved_at
- created_at

## TransferItem 转单明细

字段：

- id
- transfer_id
- participation_item_id
- quantity

## AuditLog 审计日志

字段：

- id
- actor_user_id
- action
- object_type
- object_id
- before_json
- after_json
- reason
- created_at
