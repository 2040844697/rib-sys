import { useQuery } from "@tanstack/react-query";

import { api, ApiError } from "@/lib/api";
import { ErrorState, InterfacePending, LoadingRows, PageHeader, Surface } from "@/components/ui";

export function WarehouseDispatchPage() {
  const query = useQuery({ queryKey: ["dispatch-requests"], queryFn: () => api.getDispatchRequests() });
  return (
    <div className="space-y-5">
      <PageHeader title="排发申请处理" description="从囤货工作台进入，处理申请明细、打包、国内运费和快递。" />
      {query.isLoading ? <LoadingRows rows={3} /> : null}
      {query.error instanceof ApiError && query.error.status === 404 ? <InterfacePending endpoint="GET /api/dispatch-requests" description="后端需要提供囤货人可处理的排发申请列表，以及详情和状态操作接口。" /> : null}
      {query.isError && !(query.error instanceof ApiError && query.error.status === 404) ? <ErrorState title="加载失败" description={query.error.message} /> : null}
      {query.data ? <Surface className="p-4"><pre className="overflow-auto text-xs">{JSON.stringify(query.data, null, 2)}</pre></Surface> : null}
    </div>
  );
}
