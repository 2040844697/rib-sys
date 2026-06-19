import { ArrowRight, Sparkles, UserRound } from "lucide-react";
import { Link } from "@tanstack/react-router";

import { Panel, SectionHeading, StatPill } from "@/components/ui";
import { useAuthState } from "@/lib/auth-store";

export function HomePage() {
  const auth = useAuthState();

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="欢迎回来"
        title={`嗨，${auth.user?.displayName ?? "同学"}`}
        description="首页先保留轻量版，负责承接欢迎、提醒和关键入口，后续再加教程、公告和 FAQ。"
      />

      <Panel className="overflow-hidden p-6 lg:p-8" strong>
        <div className="grid gap-5 lg:grid-cols-[1.2fr_0.8fr]">
          <div>
            <div className="chip-muted bg-white/90 text-[var(--accent-strong)]">
              <Sparkles className="size-4" />
              第一阶段已经就位
            </div>
            <h2 className="mt-4 text-3xl font-semibold tracking-tight text-slate-900">
              现在可以直接从登录走到谷团、拼团详情和管理入口
            </h2>
            <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-600">
              这版首页不追求信息量最大，而是用来收束当前进度：哪些页面已经可用，哪些还只是轻量占位，以及下一步建议从哪里继续迭代。
            </p>

            <div className="mt-6 flex flex-wrap gap-3">
              <Link to="/app/groups" className="button-primary">
                进入谷团
                <ArrowRight className="size-4" />
              </Link>
              <Link to="/app/me" className="button-secondary">
                <UserRound className="size-4" />
                查看我的资料
              </Link>
            </div>
          </div>

          <div className="grid gap-3">
            <StatPill label="当前角色" value={(auth.user?.roles ?? []).join(" / ")} />
            <StatPill label="默认入口" value={auth.defaultGroupId ?? "group_1"} accent="accent" />
            <StatPill label="Mock 状态" value="已启用" accent="teal" />
          </div>
        </div>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel className="p-5">
          <h3 className="text-lg font-semibold text-slate-900">已完成</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            登录、底部 Tab、谷团列表、谷团详情、拼团详情、管理台入口、我的资料已经能在 mock 环境里联动。
          </p>
        </Panel>
        <Panel className="p-5">
          <h3 className="text-lg font-semibold text-slate-900">占位中</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            新建拼团先保留基础表单；管理台先展示模块入口；复杂流程页下一阶段再展开。
          </p>
        </Panel>
        <Panel className="p-5">
          <h3 className="text-lg font-semibold text-slate-900">下一步</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            后续建议继续把商品图鉴、创建拼团商品编辑、拼单记录和付款状态拆成独立页面。
          </p>
        </Panel>
      </div>
    </div>
  );
}
