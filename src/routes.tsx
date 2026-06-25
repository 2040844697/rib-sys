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
import { EmptyState, Surface } from "@/components/ui";
import { authStore, useAuthState } from "@/lib/auth-store";
import { AdminAuditPage } from "@/pages/admin-audit-page";
import { AdminExceptionsPage } from "@/pages/admin-exceptions-page";
import { AdminHomePage } from "@/pages/admin-home-page";
import { AdminTransfersPage } from "@/pages/admin-transfers-page";
import { AdminUsersPage } from "@/pages/admin-users-page";
import { AddressesPage } from "@/pages/addresses-page";
import { DispatchNewPage } from "@/pages/dispatch-new-page";
import { GoodsDetailPage } from "@/pages/goods-detail-page";
import { GoodsPage } from "@/pages/goods-page";
import { GroupBuyDetailPage } from "@/pages/group-buy-detail-page";
import { GroupBuyFormPage } from "@/pages/group-buy-form-page";
import { GroupDetailPage } from "@/pages/group-detail-page";
import { GroupsPage } from "@/pages/groups-page";
import { HomePage } from "@/pages/home-page";
import { InternationalBatchNewPage } from "@/pages/international-batch-new-page";
import { LoginPage } from "@/pages/login-page";
import { MeChargesPage } from "@/pages/me-charges-page";
import { MeDispatchablePage } from "@/pages/me-dispatchable-page";
import { MePage } from "@/pages/me-page";
import { MeRecordsPage } from "@/pages/me-records-page";
import { PaymentChannelsPage } from "@/pages/payment-channels-page";
import { RegisterPage } from "@/pages/register-page";
import { WarehouseDispatchPage } from "@/pages/warehouse-dispatch-page";
import { WarehousePage } from "@/pages/warehouse-page";

function RootLayout() {
  useEffect(() => {
    void authStore.bootstrap();
  }, []);

  return <Outlet />;
}

function LoadingScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <Surface className="max-w-md p-6 text-center">
        <div className="font-semibold text-slate-950">正在连接后端接口</div>
        <p className="mt-2 text-sm text-slate-600">会话校验完成后自动进入应用。</p>
      </Surface>
    </div>
  );
}

function IndexRedirect() {
  const auth = useAuthState();
  if (auth.status === "idle" || auth.status === "loading") return <LoadingScreen />;
  if (auth.status === "authenticated") return <Navigate to="/app/groups" replace />;
  return <Navigate to="/login" replace />;
}

function AppLayout() {
  const auth = useAuthState();
  if (auth.status === "idle" || auth.status === "loading") return <LoadingScreen />;
  if (auth.status === "anonymous") return <Navigate to="/login" replace />;
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}

function NotFoundPage() {
  return (
    <div className="p-6">
      <EmptyState
        title="页面不存在"
        description="当前路由还没有页面。"
        action={<Link to="/app/groups" className="btn btn-primary">返回谷团</Link>}
      />
    </div>
  );
}

const rootRoute = createRootRoute({
  component: RootLayout,
  notFoundComponent: NotFoundPage,
});

const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", component: IndexRedirect });
const loginRoute = createRoute({ getParentRoute: () => rootRoute, path: "login", component: LoginPage });
const registerRoute = createRoute({ getParentRoute: () => rootRoute, path: "register", component: RegisterPage });
const appRoute = createRoute({ getParentRoute: () => rootRoute, path: "app", component: AppLayout });

const homeRoute = createRoute({ getParentRoute: () => appRoute, path: "home", component: HomePage });
const groupsRoute = createRoute({ getParentRoute: () => appRoute, path: "groups", component: GroupsPage });
const groupDetailRoute = createRoute({ getParentRoute: () => appRoute, path: "groups/$groupId", component: GroupDetailPage });
const groupAdminRoute = createRoute({ getParentRoute: () => appRoute, path: "groups/$groupId/admin", component: AdminHomePage });
const groupBuyNewRoute = createRoute({ getParentRoute: () => appRoute, path: "group-buys/new", component: GroupBuyFormPage });
const groupScopedBuyNewRoute = createRoute({ getParentRoute: () => appRoute, path: "groups/$groupId/group-buys/new", component: GroupBuyFormPage });
const groupBuyEditRoute = createRoute({ getParentRoute: () => appRoute, path: "group-buys/$groupBuyId/edit", component: GroupBuyFormPage });
const groupBuyDetailRoute = createRoute({ getParentRoute: () => appRoute, path: "group-buys/$groupBuyId", component: GroupBuyDetailPage });
const goodsRoute = createRoute({ getParentRoute: () => appRoute, path: "goods", component: GoodsPage });
const goodsDetailRoute = createRoute({ getParentRoute: () => appRoute, path: "goods/$goodsId", component: GoodsDetailPage });
const meRoute = createRoute({ getParentRoute: () => appRoute, path: "me", component: MePage });
const meRecordsRoute = createRoute({ getParentRoute: () => appRoute, path: "me/records", component: MeRecordsPage });
const meChargesRoute = createRoute({ getParentRoute: () => appRoute, path: "me/charges", component: MeChargesPage });
const meDispatchableRoute = createRoute({ getParentRoute: () => appRoute, path: "me/dispatchable-items", component: MeDispatchablePage });
const paymentChannelsRoute = createRoute({ getParentRoute: () => appRoute, path: "me/payment-channels", component: PaymentChannelsPage });
const addressesRoute = createRoute({ getParentRoute: () => appRoute, path: "me/addresses", component: AddressesPage });
const dispatchNewRoute = createRoute({ getParentRoute: () => appRoute, path: "dispatch-requests/new", component: DispatchNewPage });
const warehouseRoute = createRoute({ getParentRoute: () => appRoute, path: "warehouse", component: WarehousePage });
const warehouseDispatchRoute = createRoute({ getParentRoute: () => appRoute, path: "warehouse/dispatch-requests", component: WarehouseDispatchPage });
const internationalNewRoute = createRoute({ getParentRoute: () => appRoute, path: "international-batches/new", component: InternationalBatchNewPage });
const adminRoute = createRoute({ getParentRoute: () => appRoute, path: "admin", component: AdminHomePage });
const adminTransfersRoute = createRoute({ getParentRoute: () => appRoute, path: "admin/transfers", component: AdminTransfersPage });
const adminExceptionsRoute = createRoute({ getParentRoute: () => appRoute, path: "admin/exceptions", component: AdminExceptionsPage });
const adminUsersRoute = createRoute({ getParentRoute: () => appRoute, path: "admin/users", component: AdminUsersPage });
const adminAuditRoute = createRoute({ getParentRoute: () => appRoute, path: "admin/audit-logs", component: AdminAuditPage });

const routeTree = rootRoute.addChildren([
  indexRoute,
  loginRoute,
  registerRoute,
  appRoute.addChildren([
    homeRoute,
    groupsRoute,
    groupDetailRoute,
    groupAdminRoute,
    groupBuyNewRoute,
    groupScopedBuyNewRoute,
    groupBuyEditRoute,
    groupBuyDetailRoute,
    goodsRoute,
    goodsDetailRoute,
    meRoute,
    meRecordsRoute,
    meChargesRoute,
    meDispatchableRoute,
    paymentChannelsRoute,
    addressesRoute,
    dispatchNewRoute,
    warehouseRoute,
    warehouseDispatchRoute,
    internationalNewRoute,
    adminRoute,
    adminTransfersRoute,
    adminExceptionsRoute,
    adminUsersRoute,
    adminAuditRoute,
  ]),
]);

export const router = createRouter({ routeTree, scrollRestoration: true });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
