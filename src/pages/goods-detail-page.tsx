import { useQuery } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";

import { api } from "@/lib/api";
import { ErrorState, LoadingRows, PageHeader, Surface } from "@/components/ui";

export function GoodsDetailPage() {
  const { goodsId } = useParams({ from: "/app/goods/$goodsId" });
  const query = useQuery({ queryKey: ["goods-detail", goodsId], queryFn: () => api.getGoodsSnapshot(goodsId) });

  if (query.isLoading) return <LoadingRows rows={2} />;
  if (query.isError) return <ErrorState title="商品详情加载失败" description={query.error.message} />;

  const data = query.data ?? {};
  const title = String(data.name ?? data.goodsId ?? "商品详情");

  return (
    <div className="space-y-5">
      <PageHeader title={title} description="商品详情直接读取后端商品快照接口。登录后有权限用户可继续接编辑表单。" />
      <Surface className="p-5">
        <pre className="overflow-auto rounded-md bg-slate-950 p-4 text-xs leading-6 text-slate-100">
          {JSON.stringify(data, null, 2)}
        </pre>
      </Surface>
    </div>
  );
}
