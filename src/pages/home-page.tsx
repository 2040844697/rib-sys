import { Link } from "@tanstack/react-router";
import { BookOpen, PackageSearch, Users } from "lucide-react";

import { PageHeader, Surface } from "@/components/ui";

export function HomePage() {
  return (
    <div className="space-y-5">
      <PageHeader title="首页" description="第一版首页先承接教程、公告和关键入口，核心流程在谷团和我的页面里完成。" />
      <div className="grid gap-4 lg:grid-cols-3">
        <Link to="/app/groups" className="surface p-5 hover:border-cyan-300">
          <Users className="size-5 text-cyan-700" />
          <h2 className="mt-3 font-semibold text-slate-950">进入谷团</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">查看团内拼谷、进入拼团详情和工作台。</p>
        </Link>
        <Link to="/app/goods" className="surface p-5 hover:border-cyan-300">
          <PackageSearch className="size-5 text-cyan-700" />
          <h2 className="mt-3 font-semibold text-slate-950">商品图鉴</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">按关键词和角色筛选，进入商品详情。</p>
        </Link>
        <Surface className="p-5">
          <BookOpen className="size-5 text-cyan-700" />
          <h2 className="mt-3 font-semibold text-slate-950">使用教程</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">后续放登录、参团、付款、排发和转单教程。</p>
        </Surface>
      </div>
    </div>
  );
}
