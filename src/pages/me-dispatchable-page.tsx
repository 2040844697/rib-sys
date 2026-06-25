import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { api, ApiError } from "@/lib/api";
import { ErrorState, InterfacePending, LoadingRows, PageHeader, Surface } from "@/components/ui";

export function MeDispatchablePage() {
  const [selected, setSelected] = useState<string[]>([]);
  const query = useQuery({ queryKey: ["dispatchable-items"], queryFn: () => api.getDispatchableItems() });
  const items = query.data?.items ?? [];

  return (
    <div className="space-y-5">
      <PageHeader
        title="可排发商品"
        description="查看当前所有可排发商品，支持勾选或全选后申请排发。"
        action={<Link to="/app/dispatch-requests/new" className="btn btn-primary">申请排发</Link>}
      />
      {query.isLoading ? <LoadingRows rows={3} /> : null}
      {query.error instanceof ApiError && query.error.status === 404 ? <InterfacePending endpoint="GET /api/my/dispatchable-items" description="需要后端返回当前用户所有可排发库存，包含囤货人、拼团、商品、数量和 stockItemId。" /> : null}
      {query.isError && !(query.error instanceof ApiError && query.error.status === 404) ? <ErrorState title="加载失败" description={query.error.message} /> : null}
      {items.length > 0 ? (
        <Surface className="p-4">
          <button className="btn btn-secondary" onClick={() => setSelected(items.map((_, index) => String(index)))} type="button">全选</button>
          <pre className="mt-4 overflow-auto text-xs">{JSON.stringify({ selected, items }, null, 2)}</pre>
        </Surface>
      ) : null}
    </div>
  );
}
