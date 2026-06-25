import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";

import { api } from "@/lib/api";
import { ErrorState, LoadingRows, PageHeader, StatusBadge, Surface } from "@/components/ui";

const fallbackModules = [
  { title: "转单审核", to: "/app/admin/transfers" },
  { title: "异常处理", to: "/app/admin/exceptions" },
  { title: "用户与角色", to: "/app/admin/users" },
  { title: "审计日志", to: "/app/admin/audit-logs" },
];

export function AdminHomePage() {
  const params = useParams({ strict: false }) as { groupId?: string };
  const groupId = params.groupId || "group_1";
  const query = useQuery({ queryKey: ["admin-capabilities", groupId], queryFn: () => api.getAdminCapabilities(groupId) });

  return (
    <div className="space-y-5">
      <PageHeader title="管理工作台" description="根据角色展示管理能力入口。" />
      {query.isLoading ? <LoadingRows rows={2} /> : null}
      {query.isError ? <ErrorState title="管理台能力加载失败" description={query.error.message} /> : null}
      <div className="grid gap-4 lg:grid-cols-2">
        {query.data?.modules.map((module) => (
          <Surface key={module.key} className="p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-semibold text-slate-950">{module.title}</h2>
                <p className="mt-2 text-sm text-slate-600">{module.description}</p>
              </div>
              <StatusBadge value={module.enabled ? "已确认" : "已取消"} />
            </div>
          </Surface>
        ))}
        {fallbackModules.map((module) => (
          <Link key={module.to} to={module.to} className="surface p-5 hover:border-cyan-300">
            <h2 className="font-semibold text-slate-950">{module.title}</h2>
            <p className="mt-2 text-sm text-slate-600">进入独立管理页面。</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
