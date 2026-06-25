import { useQuery } from "@tanstack/react-query";

import { api, ApiError } from "@/lib/api";
import { ErrorState, InterfacePending, LoadingRows, PageHeader, Surface } from "@/components/ui";

export function AdminExceptionsPage() {
  const query = useQuery({ queryKey: ["exceptions"], queryFn: () => api.getExceptions() });
  return (
    <div className="space-y-5">
      <PageHeader title="异常处理" description="处理缺货、争议、异常付款、异常排发和退款。" />
      {query.isLoading ? <LoadingRows rows={3} /> : null}
      {query.error instanceof ApiError && query.error.status === 404 ? <InterfacePending endpoint="GET /api/exceptions" description="后端需要提供异常列表、详情和处理动作接口。" /> : null}
      {query.isError && !(query.error instanceof ApiError && query.error.status === 404) ? <ErrorState title="加载失败" description={query.error.message} /> : null}
      {query.data ? <Surface className="p-4"><pre className="overflow-auto text-xs">{JSON.stringify(query.data, null, 2)}</pre></Surface> : null}
    </div>
  );
}
