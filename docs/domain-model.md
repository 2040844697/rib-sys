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
- 真实关系应是群包含用户；第一版只有一个群组时可以先在 User 上保留 group_id，后续多群再拆出群成员关系

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
- status 第一版使用中文业务状态：等待开团、拼拼拼、已切、已截团、已完成、已取消

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
- qr_image_url 第一版指向本地 MinIO 中的对象 URL

## Charge 费用/肾

Charge 表示一笔“谁应该给谁多少钱”的费用记录，包括首款、国际费用、国内运费、补款和退款。系统只记录线下收付过程，不代表平台实际经手资金。

字段：

- id
- type
- payer_user_id
- payee_user_id
- biz_type
- biz_id
- amount_cny
- status
- payment_channel_id
- note
- snapshot_json
- created_at

说明：

- id：费用记录 ID，系统内部唯一标识
- type：费用类型，例如首款、国际费用、国内运费、补款、退款
- payer_user_id：付款方用户 ID，谁需要付这笔钱；退款场景中表示应收到退款的人时，需要在业务说明中明确方向
- payee_user_id：收款方用户 ID，这笔钱是付给谁；退款场景中表示退款发出方时，需要在业务说明中明确方向
- biz_type：关联业务类型，例如拼单、国际批次、排发申请、转单、调价
- biz_id：关联业务对象 ID，对应具体哪一个拼单、批次、排发申请或调整来源
- amount_cny：金额，单位人民币；建议实现时以后端整数分为最小存储单位
- status：费用状态，例如待支付、已提交凭证、已确认、已取消、已退款
- payment_channel_id：收款渠道 ID，对应二维码、账号或收款方式
- note：备注，用于写补充说明
- snapshot_json：费用快照，保存生成这笔费用时的关键上下文，避免后续商品、用户昵称或价格变化影响追溯
- created_at：创建时间，这笔费用是什么时候生成的
- 首款通常按用户和拼单合并生成一条 Charge
- 调价或异常处理不覆盖原始 Charge，应生成补款、退款或调整记录

## PaymentProof 付款记录

PaymentProof 表示用户提交的一次付款截图、转账证明或后续退款凭证。

字段：

- id
- submitted_by
- from_user_id
- to_user_id
- amount_cny
- paid_at
- proof_image_url
- note
- status
- reviewed_by
- reviewed_at
- reject_reason

说明：

- id：付款凭证 ID
- submitted_by：提交人 ID，谁上传了这张凭证
- from_user_id：付款人 ID，谁出的这笔钱
- to_user_id：收款人 ID，这笔钱打给了谁
- amount_cny：付款金额
- paid_at：付款时间
- proof_image_url：付款截图地址，第一版指向本地 MinIO 中的对象 URL
- note：备注，用于填写付款方式、流水说明或其他补充信息
- status：凭证状态，例如待审核、已确认、已驳回、已作废
- reviewed_by：审核人 ID，谁确认或驳回了这张凭证
- reviewed_at：审核时间
- reject_reason：驳回原因，为什么这张凭证没有通过

## PaymentProofAllocation 付款分摊关系

PaymentProofAllocation 表示一张付款凭证核销了哪些费用。它让系统后续可以支持一张付款凭证对应多笔费用，或一笔费用被多次付款覆盖。

字段：

- id
- proof_id
- charge_id
- allocated_amount_cny

说明：

- id：分摊关系 ID
- proof_id：付款凭证 ID，对应哪一张截图或付款记录
- charge_id：费用记录 ID，这张凭证核销的是哪一笔费用
- allocated_amount_cny：本次分摊到该费用上的金额

## ChargeAdjustment 费用调整记录

ChargeAdjustment 表示调价、转单、缺货、退款或人工修正带来的费用变化。调整记录只解释变化原因，实际应收或应退仍应通过 Charge 表达。

字段：

- id
- charge_id
- source_charge_id
- delta_cny
- reason
- source_type
- source_id
- approved_by
- created_at

说明：

- id：调整记录 ID
- charge_id：被调整或新生成的费用记录 ID
- source_charge_id：来源费用 ID，如果这笔调整基于另一笔费用产生，则记录来源
- delta_cny：调整差额，记录增加或减少了多少钱
- reason：调整原因，例如调价、转单、缺货、人工修正
- source_type：来源业务类型，例如调价申请、转单申请、管理员修正
- source_id：来源业务对象 ID，对应具体哪次调价或哪次转单
- approved_by：批准人 ID，谁同意了这次调整
- created_at：调整生成时间

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
- 税费默认在本次国际运输涉及的全部订单成员中均摊
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

说明：

- 转单默认由转出方和转入方先线下确认，再提交系统申请
- 系统内由拼单维护人或管理员审核通过后生效
- 已确认付款记录保留在原成员名下，后续未发生费用由新成员承担

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
