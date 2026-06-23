import { delay, http, HttpResponse } from "msw";

import {
  buildAdminCapabilities,
  buildBootstrap,
  buildGroupBuyDetail,
  buildGroupBuys,
  buildGroupHome,
  buildGroups,
  claimGroupBuyItem,
  createGroupBuy,
  getUserByAccount,
  getUserBySessionToken,
  readMe,
  updateMe,
} from "@/mock/data";
import type {
  ClaimGroupBuyPayload,
  GroupBuyCreatePayload,
  LoginRequest,
  RegisterRequest,
  UpdateMePayload,
} from "@/types";

async function jsonBody<T>(request: Request) {
  return (await request.json()) as T;
}

function requireUser(request: Request) {
  const sessionToken =
    request.headers.get("X-Session-Token") ?? request.headers.get("X-Mock-Session");
  const user = getUserBySessionToken(sessionToken);
  if (!user) {
    return HttpResponse.json(
      { code: "UNAUTHORIZED", message: "请先登录", details: null },
      { status: 401 },
    );
  }

  return user;
}

function notFound(message = "数据不存在") {
  return HttpResponse.json({ code: "NOT_FOUND", message, details: null }, { status: 404 });
}

function forbidden(message = "当前账号暂时没有权限") {
  return HttpResponse.json({ code: "FORBIDDEN", message, details: null }, { status: 403 });
}

function readParam(value: string | readonly string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export const handlers = [
  http.post("/api/auth/login", async ({ request }) => {
    await delay(400);

    const payload = await jsonBody<LoginRequest>(request);
    const user = getUserByAccount(payload.account.trim());

    if (!user || payload.password !== "123456") {
      return HttpResponse.json(
        {
          code: "UNAUTHORIZED",
          message:
            "账号或密码不正确。开发模式可使用 member / maintainer / stock / admin，密码统一为 123456。",
          details: null,
        },
        { status: 401 },
      );
    }

    return HttpResponse.json({
      userId: user.id,
      displayName: user.displayName,
      roles: user.roles,
      next: "/app/groups",
      sessionToken: user.id,
    });
  }),

  http.post("/api/auth/register", async ({ request }) => {
    await delay(500);

    const payload = await jsonBody<RegisterRequest>(request);
    if (payload.password !== payload.confirmPassword) {
      return HttpResponse.json(
        {
          code: "VALIDATION_FAILED",
          message: "两次密码输入不一致",
          details: null,
        },
        { status: 400 },
      );
    }

    return HttpResponse.json({
      ok: true,
      canLoginNow: true,
      nextAction: "login",
    });
  }),

  http.post("/api/auth/logout", async () => {
    await delay(200);
    return HttpResponse.json({ ok: true });
  }),

  http.get("/api/app/bootstrap", async ({ request }) => {
    await delay(250);

    const user = requireUser(request);
    if (user instanceof HttpResponse) {
      return user;
    }

    return HttpResponse.json(buildBootstrap(user));
  }),

  http.get("/api/app/groups", async ({ request }) => {
    await delay(300);

    const user = requireUser(request);
    if (user instanceof HttpResponse) {
      return user;
    }

    return HttpResponse.json(buildGroups(user));
  }),

  http.get("/api/app/groups/:groupId/home", async ({ params, request }) => {
    await delay(280);

    const user = requireUser(request);
    if (user instanceof HttpResponse) {
      return user;
    }

    const groupId = readParam(params.groupId);
    if (!groupId) {
      return notFound("谷团不存在");
    }

    const result = buildGroupHome(groupId, user);
    if (!result) {
      return notFound("谷团不存在");
    }

    return HttpResponse.json(result);
  }),

  http.get("/api/app/groups/:groupId/group-buys", async ({ params, request }) => {
    await delay(360);

    const user = requireUser(request);
    if (user instanceof HttpResponse) {
      return user;
    }

    const groupId = readParam(params.groupId);
    if (!groupId) {
      return notFound("谷团不存在");
    }

    const url = new URL(request.url);
    const result = buildGroupBuys(groupId, user, {
      status: url.searchParams.get("status"),
      keyword: url.searchParams.get("keyword"),
    });

    return HttpResponse.json(result);
  }),

  http.get("/api/app/groups/:groupId/admin-capabilities", async ({ request }) => {
    await delay(260);

    const user = requireUser(request);
    if (user instanceof HttpResponse) {
      return user;
    }

    const result = buildAdminCapabilities(user);
    if (!result.modules.some((item) => item.enabled)) {
      return forbidden("你当前是普通成员，暂时不能进入管理台");
    }

    return HttpResponse.json(result);
  }),

  http.get("/api/app/group-buys/:groupBuyId/detail", async ({ params, request }) => {
    await delay(320);

    const user = requireUser(request);
    if (user instanceof HttpResponse) {
      return user;
    }

    const groupBuyId = readParam(params.groupBuyId);
    if (!groupBuyId) {
      return notFound("拼团不存在");
    }

    const result = buildGroupBuyDetail(groupBuyId, user);
    if (!result) {
      return notFound("拼团不存在");
    }

    return HttpResponse.json(result);
  }),

  http.post("/api/group-buy-records", async ({ request }) => {
    await delay(450);

    const user = requireUser(request);
    if (user instanceof HttpResponse) {
      return user;
    }

    try {
      const payload = await jsonBody<ClaimGroupBuyPayload>(request);
      return HttpResponse.json(claimGroupBuyItem(payload, user));
    } catch (error) {
      return HttpResponse.json(
        {
          code: "VALIDATION_FAILED",
          message: error instanceof Error ? error.message : "认领失败",
          details: null,
        },
        { status: 400 },
      );
    }
  }),

  http.post("/api/group-buys", async ({ request }) => {
    await delay(420);

    const user = requireUser(request);
    if (user instanceof HttpResponse) {
      return user;
    }

    try {
      const payload = await jsonBody<GroupBuyCreatePayload>(request);
      return HttpResponse.json(createGroupBuy(payload, user));
    } catch (error) {
      return HttpResponse.json(
        {
          code: "VALIDATION_FAILED",
          message: error instanceof Error ? error.message : "创建失败",
          details: null,
        },
        { status: 400 },
      );
    }
  }),

  http.get("/api/me", async ({ request }) => {
    await delay(220);

    const user = requireUser(request);
    if (user instanceof HttpResponse) {
      return user;
    }

    return HttpResponse.json(readMe(user));
  }),

  http.patch("/api/me", async ({ request }) => {
    await delay(360);

    const user = requireUser(request);
    if (user instanceof HttpResponse) {
      return user;
    }

    try {
      const payload = await jsonBody<UpdateMePayload>(request);
      updateMe(user, payload);
      return HttpResponse.json({ ok: true });
    } catch (error) {
      return HttpResponse.json(
        {
          code: "VALIDATION_FAILED",
          message: error instanceof Error ? error.message : "保存失败",
          details: null,
        },
        { status: 400 },
      );
    }
  }),
];
