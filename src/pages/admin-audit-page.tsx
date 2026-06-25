import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { ErrorState, LoadingRows, PageHeader, Surface } from "@/components/ui";

export function AdminAuditPage() {
  const query = useQuery({ queryKey: ["audit-logs"], queryFn: () => api.listAuditLogs({}) });
  return (
    <div className="space-y-5">
      <PageHeader title="审计日志" description="查看关键操作记录，后续可继续加操作人、对象类型和时间筛选。" />
      {query.isLoading ? <LoadingRows rows={3} /> : null}
      {query.isError ? <ErrorState title="审计日志加载失败" description={query.error.message} /> : null}
      {query.data ? <Surface className="p-4"><pre className="overflow-auto text-xs">{JSON.stringify(query.data, null, 2)}</pre></Surface> : null}
    </div>
  );
}
