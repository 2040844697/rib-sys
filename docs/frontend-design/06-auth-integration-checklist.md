# 认证接入配合清单

本文档整理前端在接入真实 Python + PostgreSQL 登录注册系统时，需要配合调整和建议预留的点。目标是尽量不推翻现有页面，而是在现有 Vite + React 结构上平滑切换。

## 1. 本阶段可以保持不变的部分

以下部分在认证一期可以继续沿用：

- 登录请求仍为 `POST /api/auth/login`
- 注册请求仍为 `POST /api/auth/register`
- 登出请求仍为 `POST /api/auth/logout`
- 登录成功后继续调用 `GET /api/app/bootstrap`
- `src/lib/auth-store.ts` 的整体状态流可以保持不变
- `src/lib/session.ts` 仍可继续使用 `localStorage` 保存 `sessionToken`
- `src/lib/api.ts` 仍可继续通过 `X-Session-Token` 发送 token

也就是说，后端第一阶段可以做到“前端不用大改也能切到真登录”。

## 2. 建议优先配合的改动

### 2.1 登录页不要永久写死四个演示账号

当前 [src/pages/login-page.tsx](/C:/Users/n2040/Documents/Ribsys/src/pages/login-page.tsx) 里默认展示：

- `member`
- `maintainer`
- `stock`
- `admin`

建议改成下面二选一：

1. 仅在开发模式展示这些快捷按钮。
2. 由后端返回 `seedAccounts` / `demoAccounts` 后再展示。

原因：

- 正式环境不应该默认暴露演示账号提示。
- 后端后续可能只保留默认管理员，不再永远创建三种演示用户。

### 2.2 注册成功页要支持两种后端结果

当前 [src/pages/register-page.tsx](/C:/Users/n2040/Documents/Ribsys/src/pages/register-page.tsx) 基本假定注册成功后就是“已创建账号，可以直接登录”。

建议让页面支持两类返回：

- `canLoginNow = true`
- `canLoginNow = false`

这样后续如果改成“注册申请待审核”，前端不用再重做交互。

### 2.3 `ApiError` 最好读取后端 `code`

当前 [src/lib/api.ts](/C:/Users/n2040/Documents/Ribsys/src/lib/api.ts) 主要读取 `message`。

建议补充：

- `code`
- `details`

这样前端能更稳定地区分：

- `UNAUTHORIZED`
- `VALIDATION_FAILED`
- `DUPLICATED_OPERATION`
- `FORBIDDEN`

## 3. 建议预留但可以晚一点做的改动

### 3.1 为 Cookie 会话升级留接口

当前 `fetch` 没有显式设置 `credentials`。

后续若后端切到 HttpOnly Cookie，会需要在 [src/lib/api.ts](/C:/Users/n2040/Documents/Ribsys/src/lib/api.ts) 里统一补：

```ts
credentials: "include"
```

本阶段可以先不加，但建议把这件事记在待办里。

### 3.2 `sessionToken` 改成可选字段

当前 [src/types.ts](/C:/Users/n2040/Documents/Ribsys/src/types.ts) 中：

```ts
export interface LoginResponse {
  userId: string;
  displayName: string;
  roles: UserRole[];
  next: string;
  sessionToken: string;
}
```

建议未来改成兼容两种模式：

- Header token 模式：有 `sessionToken`
- Cookie 模式：没有 `sessionToken`

可以考虑改成：

```ts
sessionToken?: string;
```

但如果当前马上改动会牵扯 `authStore`，也可以等后端真正切 Cookie 时再动。

### 3.3 为登录响应预留 session 元信息

后端建议在登录响应中额外返回：

```json
{
  "session": {
    "expiresAt": "2026-06-27T12:00:00Z"
  }
}
```

前端一期可以忽略，但类型上最好允许未来追加字段。

## 4. 建议调整的类型定义

建议未来在 [src/types.ts](/C:/Users/n2040/Documents/Ribsys/src/types.ts) 做下面这些增强。

### 登录返回

```ts
export interface LoginResponse {
  userId: string;
  displayName: string;
  roles: UserRole[];
  next: string;
  sessionToken: string;
  session?: {
    expiresAt: string;
  };
}
```

### 注册返回

当前前端只接受：

```ts
{ ok: true }
```

建议后续升级为：

```ts
export interface RegisterResponse {
  ok: true;
  userId?: string;
  canLoginNow?: boolean;
  nextAction?: "login" | "wait_review";
}
```

### 用户快照

建议后续允许后端补充：

- `status`
- `capabilities`

但这不是本阶段必须。

## 5. 需要同步关注的前端文件

### [src/pages/login-page.tsx](/C:/Users/n2040/Documents/Ribsys/src/pages/login-page.tsx)

- 把演示账号快捷入口做成开发态功能
- 不要在生产文案里默认展示固定密码 `123456`

### [src/pages/register-page.tsx](/C:/Users/n2040/Documents/Ribsys/src/pages/register-page.tsx)

- 支持 `canLoginNow`
- 支持未来“申请已提交，等待审核”文案

### [src/lib/api.ts](/C:/Users/n2040/Documents/Ribsys/src/lib/api.ts)

- 读取 `code` / `details`
- 后续切 Cookie 时统一加 `credentials: "include"`

### [src/lib/auth-store.ts](/C:/Users/n2040/Documents/Ribsys/src/lib/auth-store.ts)

- 当前流程可保留
- 后续如果 `sessionToken` 变为可选，需要兼容 cookie 登录

### [src/lib/session.ts](/C:/Users/n2040/Documents/Ribsys/src/lib/session.ts)

- 当前可以保留
- 后续切 Cookie 后，这个模块会逐步退化为兼容层

### [src/mock/handlers.ts](/C:/Users/n2040/Documents/Ribsys/src/mock/handlers.ts)

- 真实后端稳定后，mock 返回结构要与正式接口保持一致
- 特别是登录、注册、bootstrap 的字段要同步

## 6. 对你现在这套前端的最小要求

如果目标只是“尽快接上真登录注册”，前端最小只需要配合三件事：

1. 保持现有登录、注册、bootstrap 调用方式不变。
2. 登录页把演示账号入口改成开发态显示。
3. 注册成功页不要把“可立即登录”写死成唯一结果。

## 7. 推荐的前后端协作顺序

1. 后端先把 PostgreSQL 登录、注册、session、默认管理员做完。
2. 前端确认登录页和注册页文案兼容真实环境。
3. 前后端一起联调 `/api/auth/login`、`/api/auth/register`、`/api/app/bootstrap`、`/api/me`。
4. 认证稳定后，再迁群组和拼团查询。

## 8. 一句话结论

前端现在不需要大改，主要是把“演示态假设”收一收，并给未来 Cookie 会话和注册审核模式预留一点弹性。
