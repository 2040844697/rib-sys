import { useQuery } from "@tanstack/react-query";

import { api, ApiError } from "@/lib/api";
import { ErrorState, InterfacePending, LoadingRows, PageHeader, Surface } from "@/components/ui";

export function AdminTransfersPage() {
  const query = useQuery({ queryKey: ["transfers"], queryFn: () => api.getTransferRequests() });
  return (
    <div className="space-y-5">
      <PageHeader title="转单审核" description="列表形式，支持多选、批量通过和不通过。" />
      {query.isLoading ? <LoadingRows rows={3} /> : null}
      {query.error instanceof ApiError && query.error.status === 404 ? <InterfacePending endpoint="GET /api/transfers / POST /api/transfers/{id}/approve" description="后端需要挂载转单列表和审核接口。" /> : null}
      {query.isError && !(query.error instanceof ApiError && query.error.status === 404) ? <ErrorState title="加载失败" description={query.error.message} /> : null}
      {query.data ? <Surface className="p-4"><pre className="overflow-auto text-xs">{JSON.stringify(query.data, null, 2)}</pre></Surface> : null}
    </div>
  );
}
