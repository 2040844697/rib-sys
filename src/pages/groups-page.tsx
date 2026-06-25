import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ChevronRight } from "lucide-react";

import { api } from "@/lib/api";
import { EmptyState, ErrorState, LoadingRows, PageHeader, RoleBadge, StatBlock, Surface } from "@/components/ui";

export function GroupsPage() {
  const query = useQuery({ queryKey: ["groups"], queryFn: () => api.getGroups() });

  return (
    <div className="space-y-5">
      <PageHeader title="谷团" description="当前即使只有一个谷团，也按列表设计，方便后续扩展多团。" />
      {query.isLoading ? <LoadingRows rows={2} /> : null}
      {query.isError ? <ErrorState title="谷团列表加载失败" description={query.error.message} /> : null}
      {query.data?.items.length === 0 ? <EmptyState title="暂无谷团" description="后端没有返回当前用户可见的谷团。" /> : null}
      <div className="grid gap-4 lg:grid-cols-2">
        {query.data?.items.map((group) => (
          <Link key={group.id} to="/app/groups/$groupId" params={{ groupId: group.id }} className="block">
            <Surface className="p-5 hover:border-cyan-300">
              <div className="flex items-start justify-between gap-4">
                <div className="flex gap-4">
                  <div className="flex size-14 shrink-0 items-center justify-center rounded-lg bg-cyan-50 text-xl font-semibold text-cyan-800">
                    {group.name.slice(0, 1)}
                  </div>
                  <div>
                    <h2 className="text-lg font-semibold text-slate-950">{group.name}</h2>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {group.myRoles.map((role) => <RoleBadge key={role} role={role} />)}
                    </div>
                  </div>
                </div>
                <ChevronRight className="size-5 text-slate-400" />
              </div>
              <div className="mt-5 grid grid-cols-2 gap-3">
                <StatBlock label="成员数" value={group.memberCount} />
                <StatBlock label="进行中拼团" value={group.activeGroupBuyCount} />
              </div>
            </Surface>
          </Link>
        ))}
      </div>
    </div>
  );
}
