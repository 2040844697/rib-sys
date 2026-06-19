import { useQuery } from "@tanstack/react-query";

import { GroupCard } from "@/components/cards";
import {
  CardSkeleton,
  EmptyState,
  ErrorState,
  Panel,
  SectionHeading,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAuthState } from "@/lib/auth-store";
import { runtimeModeLabel } from "@/lib/runtime";

export function GroupsPage() {
  const auth = useAuthState();
  const groupsQuery = useQuery({
    queryKey: ["groups"],
    queryFn: () => api.getGroups(),
  });

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="谷团"
        title="选择你要进入的谷团"
        description="当前每个谷团卡片都会直接展示我的角色、成员规模和活跃拼团数量，方便手机端快速扫读。"
      />

      <Panel className="p-6" strong>
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <div className="text-sm font-semibold text-slate-900">
              {auth.user?.displayName ?? "当前用户"}
            </div>
            <p className="mt-2 text-sm leading-7 text-slate-600">
              第一阶段的谷团列表优先突出“进入详情”这个动作。后续如果谷团数量变多，可以继续追加搜索、
              分组和最近访问等能力。
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
            <div className="rounded-[22px] bg-white/80 p-4">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500">我的角色</div>
              <div className="mt-2 text-lg font-semibold text-slate-900">
                {(auth.user?.roles ?? []).length}
              </div>
            </div>
            <div className="rounded-[22px] bg-[var(--accent-soft)] p-4 text-[var(--accent-strong)]">
              <div className="text-xs uppercase tracking-[0.2em]">当前模式</div>
              <div className="mt-2 text-lg font-semibold">{runtimeModeLabel}</div>
            </div>
          </div>
        </div>
      </Panel>

      {groupsQuery.isLoading ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <CardSkeleton lines={4} />
          <CardSkeleton lines={4} />
        </div>
      ) : null}

      {groupsQuery.isError ? (
        <ErrorState
          title="谷团列表加载失败"
          description={groupsQuery.error.message}
          action={
            <button className="button-secondary" onClick={() => groupsQuery.refetch()}>
              重试
            </button>
          }
        />
      ) : null}

      {groupsQuery.data && groupsQuery.data.items.length === 0 ? (
        <EmptyState
          title="暂无可见谷团"
          description="这里后续可以根据角色展示加入入口或申请提示。"
        />
      ) : null}

      {groupsQuery.data && groupsQuery.data.items.length > 0 ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {groupsQuery.data.items.map((group) => (
            <GroupCard key={group.id} group={group} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
