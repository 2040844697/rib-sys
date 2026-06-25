import { useQuery } from "@tanstack/react-query";

import { api, ApiError } from "@/lib/api";
import { ErrorState, InterfacePending, LoadingRows, PageHeader, Surface } from "@/components/ui";

export function MeRecordsPage() {
  const query = useQuery({ queryKey: ["my-records"], queryFn: () => api.getMyRecords() });
  return (
    <div className="space-y-5">
      <PageHeader title="我的拼单 / 我的记录" description="入口放在我的页面，支持后续勾选记录发起转单。" />
      {query.isLoading ? <LoadingRows rows={3} /> : null}
      {query.error instanceof ApiError && query.error.status === 404 ? <InterfacePending endpoint="GET /api/app/me/records" description="需要后端返回当前用户的拼单记录、商品份额、状态和关联费用。" /> : null}
      {query.isError && !(query.error instanceof ApiError && query.error.status === 404) ? <ErrorState title="加载失败" description={query.error.message} /> : null}
      {query.data ? <Surface className="p-4"><pre className="overflow-auto text-xs">{JSON.stringify(query.data, null, 2)}</pre></Surface> : null}
    </div>
  );
}
