# 前端设计说明书总览

本文档用于指导 RibSys2 第一版前端开发。第一版目标不是一次做完所有后台能力，而是尽快做出可在手机和 PC 浏览器中使用的流程界面，用来验证拼单、付款、转运、入库、排发和转单等核心流程。

## 前端定位

RibSys2 前端第一版是一个响应式 Web 应用：

- 手机浏览器优先，外观接近轻应用或小程序。
- PC 浏览器可用，同一套路由和页面在宽屏下变成工作台布局。
- 首页、谷团、我的作为底部常驻 Tab。
- 流程相关页面优先开发，首页和个人页先做轻量版本。
- 后端未完成时，前端先通过 mock API 跑通业务流程。

## 推荐技术栈

- `React`
- `TypeScript`
- `Vite`
- `TanStack Router`
- `TanStack Query`
- `React Hook Form`
- `Zod`
- `Tailwind CSS`
- `shadcn/ui` 或基于 `Radix UI` 的自定义组件
- `lucide-react`
- `MSW` 用于 mock API

说明：

- React + Vite 适合快速搭建可测前端。
- TanStack Query 适合围绕后端接口做缓存、刷新和状态同步。
- MSW 可以在后端未完成时模拟接口。
- UI 需要移动端友好，同时 PC 能展开更多列和筛选器。

## 文档结构

- [00-product-shell.md](00-product-shell.md)：产品结构、入口、Tab、角色差异
- [01-responsive-layout.md](01-responsive-layout.md)：手机和 PC 响应式布局规范
- [02-page-specs-v1.md](02-page-specs-v1.md)：第一版页面说明
- [03-components-and-states.md](03-components-and-states.md)：组件、状态标签和交互规范
- [04-frontend-api-needs.md](04-frontend-api-needs.md)：前端需要的后端聚合接口和 DTO
- [05-mock-and-development-plan.md](05-mock-and-development-plan.md)：mock 数据和开发顺序
- [07-business-page-map.md](07-business-page-map.md)：业务页面地图、入口和弹窗承载规则

## 第一版优先级

P0：

- 登录页
- App Shell
- 底部 Tab
- 谷团列表
- 谷团详情
- 拼团列表
- 拼团详情入口
- 新建拼团入口
- 管理台入口

P1：

- 商品图鉴列表和选择商品
- 创建和编辑拼团
- 拼单商品库存管理
- 拼单记录列表
- 付款状态展示
- 上传付款凭证弹窗
- 付款确认和驳回
- 上传下单截图
- 我的费用

P2：

- 转运入库
- 费用付款
- 排发申请
- 转单异常
- 管理台细化
- 商品图鉴详情
- 收款方式
- 地址簿
- 用户角色管理
- 审计日志

## 与后端文档关系

前端页面优先消费后端的“页面聚合接口”，避免一个页面为了展示基础信息调用过多细粒度领域接口。

相关后端文档：

- [../backend-development/11-frontend-facing-api.md](../backend-development/11-frontend-facing-api.md)
- [../backend-development/10-cross-module-interfaces.md](../backend-development/10-cross-module-interfaces.md)
