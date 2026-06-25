import { useQuery } from "@tanstack/react-query";

import { api, ApiError } from "@/lib/api";
import { ErrorState, InterfacePending, LoadingRows, PageHeader, Surface } from "@/components/ui";

export function MeChargesPage() {
  const query = useQuery({ queryKey: ["my-charges"], queryFn: () => api.getMyCharges() });
  return (
    <div className="space-y-5">
      <PageHeader title="我的费用" description="展示首款、国际费、国内运费、补款和退款。上传付款凭证使用弹窗。" />
      {query.isLoading ? <LoadingRows rows={3} /> : null}
      {query.error instanceof ApiError && query.error.status === 404 ? <InterfacePending endpoint="GET /api/my/charges" description="后端需要提供当前用户费用列表，供付款和状态查询使用。" /> : null}
      {query.isError && !(query.error instanceof ApiError && query.error.status === 404) ? <ErrorState title="加载失败" description={query.error.message} /> : null}
      {query.data ? <Surface className="p-4"><pre className="overflow-auto text-xs">{JSON.stringify(query.data, null, 2)}</pre></Surface> : null}
    </div>
  );
}
