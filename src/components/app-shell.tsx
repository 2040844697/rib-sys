import type { ReactNode } from "react";
import { House, UserRound, Users } from "lucide-react";
import { Link, useLocation } from "@tanstack/react-router";

import { useAuthState } from "@/lib/auth-store";
import { cn } from "@/lib/utils";

const navItems = [
  {
    key: "home",
    label: "首页",
    to: "/app/home",
    icon: House,
    match: (pathname: string) => pathname === "/app/home",
  },
  {
    key: "groups",
    label: "谷团",
    to: "/app/groups",
    icon: Users,
    match: (pathname: string) =>
      pathname.startsWith("/app/groups") || pathname.startsWith("/app/group-buys"),
  },
  {
    key: "me",
    label: "我的",
    to: "/app/me",
    icon: UserRound,
    match: (pathname: string) => pathname.startsWith("/app/me"),
  },
];

function getPageMeta(pathname: string) {
  if (pathname.startsWith("/app/groups/") && pathname.endsWith("/admin")) {
    return {
      title: "管理台",
      description: "先用模块入口版承接角色差异，后续再拆具体工作面板。",
    };
  }

  if (pathname.startsWith("/app/groups/")) {
    return {
      title: "谷团详情",
      description: "团信息、管理入口与拼团列表集中在一页完成。",
    };
  }

  if (pathname.startsWith("/app/group-buys/new")) {
    return {
      title: "新建拼团",
      description: "先把基础字段和导航链路跑通，商品编辑后续补细。",
    };
  }

  if (pathname.startsWith("/app/group-buys/")) {
    return {
      title: "拼团详情",
      description: "成员认领与维护入口先集中在这个首屏版本里。",
    };
  }

  if (pathname.startsWith("/app/me")) {
    return {
      title: "我的",
      description: "维护个人信息、角色展示和退出登录。",
    };
  }

  if (pathname.startsWith("/app/home")) {
    return {
      title: "首页",
      description: "第一版先保留轻量欢迎页和下一步入口。",
    };
  }

  return {
    title: "谷团",
    description: "移动端优先的拼团工作流，先把核心路径做通。",
  };
}

export function AppShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const auth = useAuthState();
  const pageMeta = getPageMeta(pathname);

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[280px_minmax(0,1fr)]">
      <aside className="hidden border-r border-white/60 bg-white/45 px-5 py-6 backdrop-blur-xl lg:flex lg:flex-col">
        <Link
          to="/app/groups"
          className="rounded-[26px] bg-slate-900 px-5 py-4 text-white shadow-[0_20px_40px_rgba(22,32,51,0.18)]"
        >
          <div className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-300">
            RibSys
          </div>
          <div className="mt-1 text-2xl font-semibold">前端第一阶段</div>
          <p className="mt-2 text-sm leading-6 text-slate-300">
            先把登录、谷团、拼团和角色差异落成可迭代界面。
          </p>
        </Link>

        <nav className="mt-6 flex flex-col gap-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = item.match(pathname);
            return (
              <Link
                key={item.key}
                to={item.to}
                className={cn(
                  "flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold transition",
                  active
                    ? "bg-white text-slate-900 shadow-sm"
                    : "text-slate-600 hover:bg-white/75",
                )}
              >
                <Icon className="size-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto rounded-[24px] border border-white/70 bg-white/78 p-4">
          <div className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--accent)]">
            当前用户
          </div>
          <div className="mt-2 text-lg font-semibold text-slate-900">
            {auth.user?.displayName ?? "未登录"}
          </div>
          <div className="text-sm text-slate-500">
            {auth.user?.groupNickname ?? "请先完成登录"}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {(auth.user?.roles ?? []).map((role) => (
              <span key={role} className="chip-muted bg-slate-50">
                {role}
              </span>
            ))}
          </div>
        </div>
      </aside>

      <div className="min-h-screen">
        <header className="sticky top-0 z-20 border-b border-white/60 bg-[rgba(251,247,242,0.84)] backdrop-blur-xl">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4 lg:px-8">
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--accent)]">
                RibSys
              </div>
              <h1 className="mt-1 text-xl font-semibold tracking-tight text-slate-900">
                {pageMeta.title}
              </h1>
              <p className="mt-1 hidden text-sm text-slate-500 sm:block">
                {pageMeta.description}
              </p>
            </div>
            <div className="chip-muted bg-white/80 text-slate-700">
              <span className="size-2 rounded-full bg-emerald-500" />
              Mock API
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-6xl px-4 pb-28 pt-6 lg:px-8 lg:pb-8">
          {children}
        </main>

        <nav className="fixed inset-x-0 bottom-0 z-20 border-t border-white/60 bg-[rgba(251,247,242,0.92)] px-4 pb-[calc(env(safe-area-inset-bottom)+12px)] pt-3 backdrop-blur-xl lg:hidden">
          <div className="mx-auto grid max-w-xl grid-cols-3 gap-2">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = item.match(pathname);
              return (
                <Link
                  key={item.key}
                  to={item.to}
                  className={cn(
                    "flex flex-col items-center gap-1 rounded-2xl px-3 py-2 text-xs font-semibold transition",
                    active
                      ? "bg-slate-900 text-white shadow-sm"
                      : "text-slate-500 hover:bg-white",
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
