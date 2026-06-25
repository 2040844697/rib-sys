import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import { Edit, FileImage, ReceiptText } from "lucide-react";

import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import {
  Button,
  EmptyState,
  ErrorState,
  Field,
  LoadingRows,
  PageHeader,
  StatBlock,
  StatusBadge,
  Surface,
  TextArea,
  TextInput,
} from "@/components/ui";

export function GroupBuyDetailPage() {
  const { groupBuyId } = useParams({ from: "/app/group-buys/$groupBuyId" });
  const queryClient = useQueryClient();
  const [proofOpen, setProofOpen] = useState(false);
  const [screenshotOpen, setScreenshotOpen] = useState(false);

  const query = useQuery({ queryKey: ["group-buy-detail", groupBuyId], queryFn: () => api.getGroupBuyDetail(groupBuyId) });
  const claim = useMutation({
    mutationFn: api.claimGroupBuy,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["group-buy-detail", groupBuyId] }),
  });
  const screenshot = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.addOrderScreenshot(payload),
    onSuccess: () => setScreenshotOpen(false),
  });

  if (query.isLoading) return <LoadingRows rows={3} />;
  if (query.isError) return <ErrorState title="拼团详情加载失败" description={query.error.message} />;
  if (!query.data) return <EmptyState title="拼团不存在" description="后端没有返回该拼团。" />;

  const { groupBuy, items, myRecords, capabilities } = query.data;

  return (
    <div className="space-y-5">
      <PageHeader
        title={groupBuy.title}
        description={groupBuy.description || "拼团详情承载认领、付款、维护和下单截图。"}
        action={
          <>
            {capabilities.canEdit ? <Link to="/app/group-buys/$groupBuyId/edit" params={{ groupBuyId }} className="btn btn-secondary"><Edit className="size-4" />编辑</Link> : null}
            <Button variant="secondary" onClick={() => setProofOpen(true)}><ReceiptText className="size-4" />上传付款凭证</Button>
            {capabilities.canUploadOrderScreenshot ? <Button variant="secondary" onClick={() => setScreenshotOpen(true)}><FileImage className="size-4" />上传下单截图</Button> : null}
          </>
        }
      />

      <Surface className="p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge value={groupBuy.status} />
            <span className="badge-neutral">{groupBuy.type}</span>
            <span className="badge-neutral">截团 {formatDateTime(groupBuy.closeAt)}</span>
          </div>
          <Link to="/app/international-batches/new" className="btn btn-secondary">创建国际转运批次</Link>
        </div>
      </Surface>

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          {items.map((item) => (
            <Surface key={item.id} className="p-4">
              <div className="grid gap-4 sm:grid-cols-[72px_1fr_auto] sm:items-center">
                <div className="flex size-16 items-center justify-center rounded-lg bg-slate-100 text-xl font-semibold text-cyan-800">
                  {item.name.slice(0, 1)}
                </div>
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge value={item.status} />
                    {(item.characterNames || (item.characterName ? [item.characterName] : [])).map((name) => <span key={name} className="badge-neutral">{name}</span>)}
                  </div>
                  <h3 className="mt-2 font-semibold text-slate-950">{item.name}</h3>
                  <p className="mt-1 text-sm text-slate-500">¥{item.unitPriceCny} · 已认领 {item.claimedQuantity}/{item.totalQuantity} · 可拼 {item.availableQuantity}</p>
                </div>
                {capabilities.canClaim ? (
                  <Button
                    busy={claim.isPending}
                    disabled={item.availableQuantity <= 0}
                    onClick={() => claim.mutate({ groupBuyId, groupBuyItemId: item.id, quantity: 1 })}
                  >
                    认领 1
                  </Button>
                ) : null}
              </div>
            </Surface>
          ))}
          {claim.error ? <ErrorState title="认领失败" description={claim.error.message} /> : null}
        </div>

        <Surface className="p-4">
          <h2 className="font-semibold text-slate-950">我的记录</h2>
          <div className="mt-3 space-y-3">
            {myRecords.length === 0 ? <p className="text-sm text-slate-500">还没有记录。</p> : null}
            {myRecords.map((record) => (
              <div key={record.id} className="rounded-md border border-slate-200 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold">数量 {record.quantity}</span>
                  <StatusBadge value={record.displayStatus} />
                </div>
                <div className="mt-2 text-xs text-slate-500">商品 {record.groupBuyItemId}</div>
              </div>
            ))}
          </div>
        </Surface>
      </div>

      {proofOpen ? (
        <Dialog title="上传付款凭证" onClose={() => setProofOpen(false)}>
          <Field label="付款金额"><TextInput placeholder="例如 35.00" /></Field>
          <Field label="付款时间"><TextInput type="datetime-local" /></Field>
          <Field label="付款截图 URL"><TextInput placeholder="先填写后端文件对象 URL" /></Field>
          <Field label="备注"><TextArea placeholder="付款方式、流水说明等" /></Field>
          <div className="flex gap-2">
            <Button onClick={() => setProofOpen(false)}>提交</Button>
            <Button variant="secondary" onClick={() => setProofOpen(false)}>取消</Button>
          </div>
        </Dialog>
      ) : null}

      {screenshotOpen ? (
        <Dialog title="上传下单截图" onClose={() => setScreenshotOpen(false)}>
          <Field label="下单截图 URL"><TextInput id="order-url" placeholder="文件上传后返回的 URL" /></Field>
          <Field label="下单时间"><TextInput id="ordered-at" type="datetime-local" /></Field>
          <Field label="备注"><TextArea id="order-note" /></Field>
          {screenshot.error ? <p className="text-sm text-rose-600">{screenshot.error.message}</p> : null}
          <div className="flex gap-2">
            <Button
              busy={screenshot.isPending}
              onClick={() =>
                screenshot.mutate({
                  groupBuyId,
                  orderScreenshotUrl: (document.getElementById("order-url") as HTMLInputElement | null)?.value,
                  orderedAt: (document.getElementById("ordered-at") as HTMLInputElement | null)?.value,
                  note: (document.getElementById("order-note") as HTMLTextAreaElement | null)?.value,
                  items: [],
                })
              }
            >
              提交
            </Button>
            <Button variant="secondary" onClick={() => setScreenshotOpen(false)}>取消</Button>
          </div>
        </Dialog>
      ) : null}
    </div>
  );
}

function Dialog({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end bg-slate-950/30 p-0 sm:items-center sm:justify-center sm:p-4">
      <Surface className="w-full space-y-4 rounded-b-none p-5 sm:max-w-xl sm:rounded-lg">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-slate-950">{title}</h3>
          <button className="btn btn-quiet" onClick={onClose} type="button">关闭</button>
        </div>
        {children}
      </Surface>
    </div>
  );
}
