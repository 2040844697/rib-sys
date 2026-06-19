import { useState } from "react";
import { Link, useParams } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Pencil, Upload } from "lucide-react";

import {
  Button,
  CardSkeleton,
  EmptyState,
  ErrorState,
  Panel,
  SectionHeading,
  StatusBadge,
  TextInput,
} from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

export function GroupBuyDetailPage() {
  const { groupBuyId } = useParams({ from: "/app/group-buys/$groupBuyId" });
  const queryClient = useQueryClient();
  const [draftQuantities, setDraftQuantities] = useState<Record<string, string>>({});

  const detailQuery = useQuery({
    queryKey: ["group-buy-detail", groupBuyId],
    queryFn: () => api.getGroupBuyDetail(groupBuyId),
  });

  const claimMutation = useMutation({
    mutationFn: api.claimGroupBuy,
    onSuccess: () => {
      setDraftQuantities({});
      void queryClient.invalidateQueries({ queryKey: ["group-buy-detail", groupBuyId] });
      void queryClient.invalidateQueries({ queryKey: ["group-buys"] });
      void queryClient.invalidateQueries({ queryKey: ["group-home"] });
    },
  });

  if (detailQuery.isLoading) {
    return (
      <div className="space-y-4">
        <CardSkeleton lines={5} />
        <CardSkeleton lines={4} />
        <CardSkeleton lines={4} />
      </div>
    );
  }

  if (detailQuery.isError) {
    return (
      <ErrorState
        title="拼团详情加载失败"
        description={detailQuery.error.message}
        action={
          <button className="button-secondary" onClick={() => detailQuery.refetch()}>
            重试
          </button>
        }
      />
    );
  }

  if (!detailQuery.data) {
    return (
      <EmptyState
        title="拼团不存在"
        description="当前 mock 数据里没有找到这个拼团。"
        action={<Link to="/app/groups" className="button-secondary">返回谷团</Link>}
      />
    );
  }

  const { groupBuy, items, myRecords, capabilities } = detailQuery.data;

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Group Buy"
        title={groupBuy.title}
        description={groupBuy.description}
      />

      <Panel className="p-6" strong>
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge value={groupBuy.status} />
              <span className="chip-muted">{groupBuy.type}</span>
            </div>
            <div className="text-sm text-slate-500">截团时间 {formatDateTime(groupBuy.closeAt)}</div>
          </div>

          <div className="flex flex-wrap gap-3">
            {capabilities.canEdit ? (
              <Button variant="secondary">
                <Pencil className="size-4" />
                编辑拼团
              </Button>
            ) : null}
            {capabilities.canUploadOrderScreenshot ? (
              <Button variant="secondary">
                <Upload className="size-4" />
                上传下单截图
              </Button>
            ) : null}
            {capabilities.canManageRecords ? (
              <Button variant="secondary">
                <Archive className="size-4" />
                查看拼单记录
              </Button>
            ) : null}
          </div>
        </div>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-[0.92fr_1.08fr]">
        <Panel className="p-5">
          <h2 className="text-lg font-semibold text-slate-900">我的记录摘要</h2>
          <p className="mt-2 text-sm text-slate-600">
            认领后会直接生成业务状态，第一版先以“未肾”作为默认回执。
          </p>
          <div className="mt-4 space-y-3">
            {myRecords.length === 0 ? (
              <div className="rounded-[22px] bg-white/80 p-4 text-sm text-slate-500">
                你还没有认领任何商品。
              </div>
            ) : (
              myRecords.map((record) => (
                <div
                  key={record.id}
                  className="rounded-[22px] border border-white/70 bg-white/80 p-4"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-slate-900">
                        商品 ID: {record.groupBuyItemId}
                      </div>
                      <div className="mt-1 text-xs text-slate-500">
                        数量 {record.quantity}
                      </div>
                    </div>
                    <StatusBadge value={record.displayStatus} />
                  </div>
                </div>
              ))
            )}
          </div>
        </Panel>

        <div className="space-y-4">
          {items.length === 0 ? (
            <EmptyState
              title="还没有拼团商品"
              description="这里先允许创建一个空拼团，后续把商品图鉴和条目编辑接进来即可。"
            />
          ) : null}

          {items.map((item) => {
            const progress =
              item.totalQuantity === 0
                ? 0
                : Math.round((item.claimedQuantity / item.totalQuantity) * 100);
            const value = draftQuantities[item.id] ?? "1";

            return (
              <Panel key={item.id} className="p-5">
                <div className="flex flex-col gap-4">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusBadge value={item.status} />
                        <span className="chip-muted">{item.characterName}</span>
                      </div>
                      <h3 className="mt-2 text-lg font-semibold text-slate-900">
                        {item.name}
                      </h3>
                      <p className="mt-1 text-sm text-slate-500">
                        单价 ¥{item.unitPriceCny} · 已认领 {item.claimedQuantity} / {item.totalQuantity}
                      </p>
                    </div>
                    <div className="text-right text-sm font-semibold text-slate-600">
                      剩余 {item.availableQuantity}
                    </div>
                  </div>

                  <div className="h-2 rounded-full bg-slate-200">
                    <div
                      className="h-full rounded-full bg-[var(--accent)] transition-all"
                      style={{ width: `${progress}%` }}
                    />
                  </div>

                  {capabilities.canClaim ? (
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                      <TextInput
                        type="number"
                        min={1}
                        max={item.availableQuantity}
                        value={value}
                        onChange={(event) =>
                          setDraftQuantities((current) => ({
                            ...current,
                            [item.id]: event.target.value,
                          }))
                        }
                        className="sm:max-w-36"
                      />
                      <Button
                        busy={claimMutation.isPending}
                        disabled={item.availableQuantity === 0}
                        onClick={() =>
                          claimMutation.mutate({
                            groupBuyId,
                            groupBuyItemId: item.id,
                            quantity: Number(value),
                          })
                        }
                      >
                        认领商品
                      </Button>
                    </div>
                  ) : (
                    <div className="rounded-[20px] bg-slate-50 p-4 text-sm text-slate-500">
                      当前角色以查看为主，不提供认领入口。
                    </div>
                  )}
                </div>
              </Panel>
            );
          })}

          {claimMutation.error ? (
            <ErrorState
              title="认领失败"
              description={claimMutation.error.message}
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}
