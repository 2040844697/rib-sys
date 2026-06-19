import { useEffect } from "react";
import {
  createRootRoute,
  createRoute,
  createRouter,
  Link,
  Navigate,
  Outlet,
} from "@tanstack/react-router";

import { AppShell } from "@/components/app-shell";
import { Panel } from "@/components/ui";
import { authStore, useAuthState } from "@/lib/auth-store";
import { AdminPage } from "@/pages/admin-page";
import { GroupBuyDetailPage } from "@/pages/group-buy-detail-page";
import { GroupBuyNewPage } from "@/pages/group-buy-new-page";
import { GroupDetailPage } from "@/pages/group-detail-page";
import { GroupsPage } from "@/pages/groups-page";
import { HomePage } from "@/pages/home-page";
import { LoginPage } from "@/pages/login-page";
import { MePage } from "@/pages/me-page";
import { RegisterPage } from "@/pages/register-page";

function RootLayout() {
  useEffect(() => {
    void authStore.bootstrap();
  }, []);

  return <Outlet />;
}

function FullscreenState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-8">
      <Panel className="max-w-xl p-8 text-center" strong>
        <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
        <p className="mt-3 text-sm leading-7 text-slate-600">{description}</p>
      </Panel>
    </div>
  );
}

function IndexRedirect() {
  const auth = useAuthState();

  if (auth.status === "idle" || auth.status === "loading") {
    return (
      <FullscreenState
        title="正在准备前端环境"
        description="正在读取 mock 会话、当前用户和默认谷团。"
      />
    );
  }

  if (auth.status === "authenticated") {
    return <Navigate to="/app/groups" replace />;
  }

  return <Navigate to="/login" replace />;
}

function AppLayout() {
  const auth = useAuthState();

  if (auth.status === "idle" || auth.status === "loading") {
    return (
      <FullscreenState
        title="正在进入工作区"
        description="当前会话校验完成后会自动跳转到谷团列表。"
      />
    );
  }

  if (auth.status === "anonymous") {
    return <Navigate to="/login" replace />;
  }

  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}

function NotFoundPage() {
  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-8">
      <Panel className="max-w-xl p-8 text-center" strong>
        <div className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--accent)]">
          404
        </div>
        <h1 className="mt-3 text-3xl font-semibold text-slate-900">页面还没落地到这里</h1>
        <p className="mt-3 text-sm leading-7 text-slate-600">
          这个路由暂时不在第一阶段实现范围内。我们已经把主要业务链路铺好，后续可以继续往这边扩。
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <Link to="/app/groups" className="button-primary">
            返回谷团
          </Link>
          <Link to="/login" className="button-secondary">
            回到登录
          </Link>
        </div>
      </Panel>
    </div>
  );
}

const rootRoute = createRootRoute({
  component: RootLayout,
  notFoundComponent: NotFoundPage,
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: IndexRedirect,
});

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "login",
  component: LoginPage,
});

const registerRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "register",
  component: RegisterPage,
});

const appRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "app",
  component: AppLayout,
});

const homeRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "home",
  component: HomePage,
});

const groupsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "groups",
  component: GroupsPage,
});

const groupDetailRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "groups/$groupId",
  component: GroupDetailPage,
});

const adminRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "groups/$groupId/admin",
  component: AdminPage,
});

const newGroupBuyRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "group-buys/new",
  component: GroupBuyNewPage,
});

const groupBuyDetailRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "group-buys/$groupBuyId",
  component: GroupBuyDetailPage,
});

const meRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "me",
  component: MePage,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  loginRoute,
  registerRoute,
  appRoute.addChildren([
    homeRoute,
    groupsRoute,
    groupDetailRoute,
    adminRoute,
    newGroupBuyRoute,
    groupBuyDetailRoute,
    meRoute,
  ]),
]);

export const router = createRouter({
  routeTree,
  scrollRestoration: true,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
