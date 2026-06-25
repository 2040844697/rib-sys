import type { ReactNode } from "react";
import {
  Boxes,
  ClipboardList,
  Home,
  PackageSearch,
  User,
  Users,
  Warehouse,
} from "lucide-react";
import { Link, useLocation } from "@tanstack/react-router";

import { useAuthState } from "@/lib/auth-store";
import { cn, formatRole } from "@/lib/utils";

const navItems = [
  {
    label: "首页",
    to: "/app/home",
    icon: Home,
    match: (path: string) => path.startsWith("/app/home"),
  },
  {
    label: "谷团",
    to: "/app/groups",
    icon: Users,
    match: (path: string) => path.startsWith("/app/groups") || path.startsWith("/app/group-buys"),
  },
  {
    label: "我的",
    to: "/app/me",
    icon: User,
    match: (path: string) => path.startsWith("/app/me") || path.startsWith("/app/dispatch-requests"),
  },
];

const workItems = [
  { label: "商品图鉴", to: "/app/goods", icon: PackageSearch },
  { label: "囤货工作台", to: "/app/warehouse", icon: Warehouse },
  { label: "管理工作台", to: "/app/admin", icon: ClipboardList },
];

function pageTitle(pathname: string) {
  if (pathname.startsWith("/app/goods")) return "商品图鉴";
  if (pathname.startsWith("/app/warehouse")) return "囤货工作台";
  if (pathname.startsWith("/app/admin")) return "管理工作台";
  if (pathname.startsWith("/app/group-buys/new")) return "新建拼团";
  if (pathname.includes("/edit")) return "编辑拼团";
  if (pathname.startsWith("/app/group-buys")) return "拼团详情";
  if (pathname.startsWith("/app/groups/")) return "谷团详情";
  if (pathname.startsWith("/app/groups")) return "谷团";
  if (pathname.startsWith("/app/me")) return "我的";
  return "首页";
}

export function AppShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const auth = useAuthState();

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <aside className="hidden border-r border-slate-200 bg-white lg:block">
        <div className="flex min-h-screen flex-col p-4">
          <Link to="/app/groups" className="flex items-center gap-3 rounded-lg bg-slate-950 p-4 text-white">
            <Boxes className="size-6" />
            <div>
              <div className="text-sm font-semibold">RibSys</div>
              <div className="text-xs text-slate-300">拼团流程工作台</div>
            </div>
          </Link>

          <nav className="mt-5 space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = item.match(pathname);
              return (
                <Link
                  key={item.label}
                  to={item.to}
                  className={cn(
                    "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-semibold",
                    active ? "bg-cyan-50 text-cyan-800" : "text-slate-600 hover:bg-slate-50",
                  )}
                >
                  <Icon className="size-4" />
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="mt-6 border-t border-slate-200 pt-4">
            <div className="px-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
              工作台
            </div>
            <nav className="mt-2 space-y-1">
              {workItems.map((item) => {
                const Icon = item.icon;
                const active = pathname.startsWith(item.to);
                return (
                  <Link
                    key={item.label}
                    to={item.to}
                    className={cn(
                      "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-semibold",
                      active ? "bg-cyan-50 text-cyan-800" : "text-slate-600 hover:bg-slate-50",
                    )}
                  >
                    <Icon className="size-4" />
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>

          <div className="mt-auto rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="text-sm font-semibold text-slate-950">
              {auth.user?.displayName ?? "未登录"}
            </div>
            <div className="mt-1 text-xs text-slate-500">{auth.user?.groupNickname}</div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {(auth.user?.roles ?? []).map((role) => (
                <span key={role} className="rounded bg-white px-2 py-1 text-xs text-slate-600">
                  {formatRole(role)}
                </span>
              ))}
            </div>
          </div>
        </div>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 lg:px-6">
            <div>
              <div className="text-xs font-semibold text-cyan-700">RibSys</div>
              <h1 className="text-lg font-semibold text-slate-950">{pageTitle(pathname)}</h1>
            </div>
            <div className="hidden text-sm text-slate-500 sm:block">后端 API 驱动</div>
          </div>
        </header>

        <main className="mx-auto max-w-7xl px-4 pb-24 pt-5 lg:px-6 lg:pb-8">{children}</main>

        <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white px-3 pb-[calc(env(safe-area-inset-bottom)+8px)] pt-2 lg:hidden">
          <div className="grid grid-cols-3 gap-2">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = item.match(pathname);
              return (
                <Link
                  key={item.label}
                  to={item.to}
                  className={cn(
                    "flex flex-col items-center gap-1 rounded-md px-2 py-2 text-xs font-semibold",
                    active ? "bg-cyan-50 text-cyan-800" : "text-slate-500",
                  )}
                >
                  <Icon className="size-4" />
                  {item.label}
                </Link>
              );
            })}
          </div>
        </nav>
      </div>
    </div>
  );
}
