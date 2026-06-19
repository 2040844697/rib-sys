# 状态机草案

## 拼单状态

- 等待开团：拼单已创建，但还没有正式开放成员参团
- 拼拼拼：正在拼团中，尚未下单，成员可以直接选择商品参团
- 已切：已经完成下单，但仍有剩余份额继续拼出
- 已截团：不再接受新的参团或认领，进入后续履约、转运、囤货和排发流程
- 已完成：该拼单相关商品份额、费用和排发流程已经处理完成
- 已取消：拼单作废，不再继续

状态流转：

等待开团 -> 拼拼拼 -> 已截团 -> 已完成

或：

等待开团 -> 拼拼拼 -> 已切 -> 已截团 -> 已完成

异常流转：

等待开团 / 拼拼拼 / 已切 / 已截团 -> 已取消

说明：

- 第一版直接使用中文业务状态作为产品展示状态，后端实现时可以再映射为枚举值
- “拼拼拼”表示还没有下单，主要用于试拼和成员直接参团
- “已切”表示已经下单，但仍可继续认领或拼出部分商品
- “已截团”表示对外拼团结束，但不代表费用、转运或排发已经完成

## 成员商品份额状态

成员商品份额表示某个成员在某个拼单商品中拥有的数量。

- reserved：已参团，待确认
- active：有效
- cancelled：已取消
- transferred：已转出
- jp_ordered：已随日本订单下单
- jp_warehouse：已到日本仓
- international_shipping：国际转运中
- domestic_stocked：已到国内囤货
- dispatchable：可排发
- dispatch_requested：已申请排发
- domestic_shipping：国内发货中
- completed：已完成

说明：

- 转单后，原份额进入 transferred，新成员获得新的 active 或后续状态份额
- dispatchable 之后可被成员选入排发申请
- 已进入排发申请的份额不应再被其他申请选择

## 日本订单状态

- created：已记录
- ordered：已下单
- shipped_to_forwarder：已发往转运
- arrived_forwarder：已到日本转运仓
- included_in_batch：已加入国际转运批次
- cancelled：已取消

## 国际转运批次状态

- draft：草稿
- preparing：准备发出
- shipped：国际运输中
- taxed：已产生税费
- arrived_domestic：已到国内
- stocked：已入库
- closed：已关闭

## 排发申请状态

- draft：草稿
- submitted：已提交
- reviewing：囤货人处理中
- packed：已打包
- domestic_fee_pending：待收国内运费
- domestic_fee_confirmed：国内运费已确认
- shipped：已发货
- completed：已完成
- cancelled：已取消

如果国内运费为到付，可以从 packed 直接流转到 shipped。

## 费用状态

费用记录用于表达“某人应付某笔钱给某个收款方”。

- pending：待付款
- submitted：成员已提交付款记录
- confirmed：已确认
- rejected：付款记录被驳回
- waived：无需支付或已免除
- refunded：已退款
- cancelled：已取消

费用类型：

- initial_goods：首款商品款
- international：国际费用
- domestic_shipping：国内运费
- adjustment：补款
- refund：退款

说明：

- 费用记录不代表平台收款，只记录线下应收、付款凭证和确认结果
- 调价、转单、缺货、退款等变化不覆盖原始费用，应通过新的补款、退款或调整记录体现

## 付款记录状态

- submitted：已提交
- confirmed：已确认
- rejected：已驳回
- voided：已作废

付款记录可关联一个费用，也可在后续支持一个付款记录抵扣多个费用。

## 调价审核状态

调价发生在已有付款或已生成应收之后时，需要审核。

- pending_review：待审核
- approved：已通过
- rejected：已拒绝
- applied：已应用
- cancelled：已取消

审核通过后，系统应生成补款或退款记录，并保留原始参团价格。
