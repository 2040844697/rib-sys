import { useParams } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import { EmptyState, ErrorState, Panel, SectionHeading, StatusBadge } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

export function AdminPage() {
  const { groupId } = useParams({ from: "/app/groups/$groupId/admin" });

  const adminQuery = useQuery({
    queryKey: ["admin-capabilities", groupId],
    queryFn: () => api.getAdminCapabilities(groupId),
  });

  if (adminQuery.isLoading) {
    return (
      <Panel className="p-6">
        <div className="animate-pulse space-y-3">
          <div className="h-6 w-40 rounded-full bg-slate-200" />
          <div className="h-4 w-full rounded-full bg-slate-200" />
          <div className="h-4 w-2/3 rounded-full bg-slate-200" />
        </div>
      </Panel>
    );
  }

  if (adminQuery.isError) {
    const error = adminQuery.error;
    if (error instanceof ApiError && error.status === 403) {
      return (
        <EmptyState
          title="你当前还不能进入管理台"
          description={error.message}
        />
      );
    }

    return (
      <ErrorState
        title="管理台加载失败"
        description={error.message}
        action={
          <button className="button-secondary" onClick={() => adminQuery.refetch()}>
            重试
          </button>
        }
      />
    );
  }

  if (!adminQuery.data) {
    return (
      <EmptyState
        title="暂无可展示模块"
        description="这里后续会继续细化成分角色工作面板。"
      />
    );
  }

  const enabledCount = adminQuery.data.modules.filter((item) => item.enabled).length;

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Admin"
        title="管理台模块入口"
        description="第一版先展示当前角色能看到的模块，后续再按业务流拆成独立工作页。"
      />

      <Panel className="p-6" strong>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="text-sm font-semibold text-slate-900">谷团 ID: {groupId}</div>
            <p className="mt-2 text-sm leading-7 text-slate-600">
              当前共返回 {adminQuery.data.modules.length} 个模块，其中 {enabledCount} 个可直接使用。
            </p>
          </div>
          <StatusBadge value={enabledCount > 0 ? "可排发" : "已取消"} />
        </div>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        {adminQuery.data.modules.map((module) => (
          <Panel key={module.key} className="p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-lg font-semibold text-slate-900">{module.title}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-600">{module.description}</p>
              </div>
              <StatusBadge value={module.enabled ? "可排发" : "已截团"} />
            </div>

            <div className="mt-5 rounded-[20px] bg-slate-50 p-4 text-sm text-slate-600">
              {module.enabled
                ? "当前角色可以看到这个入口。下一轮可以继续拆成列表页、详情页和操作表单。"
                : "当前角色暂未开放这个模块，但入口结构已经预留，后续接角色能力即可。"}
            </div>
          </Panel>
        ))}
      </div>
    </div>
  );
}
