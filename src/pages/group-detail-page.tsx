import { useDeferredValue, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import { Plus, Settings } from "lucide-react";

import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import {
  DataGrid,
  EmptyState,
  ErrorState,
  LoadingRows,
  PageHeader,
  SearchBox,
  StatBlock,
  StatusBadge,
  Surface,
} from "@/components/ui";

const statusFilters = ["全部", "进行中", "未开始", "已截团", "已完成", "已取消"];

export function GroupDetailPage() {
  const { groupId } = useParams({ from: "/app/groups/$groupId" });
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState("进行中");
  const deferredKeyword = useDeferredValue(keyword);

  const homeQuery = useQuery({ queryKey: ["group-home", groupId], queryFn: () => api.getGroupHome(groupId) });
  const buysQuery = useQuery({
    queryKey: ["group-buys", groupId, status, deferredKeyword],
    queryFn: () => api.getGroupBuys(groupId, { status: status === "全部" ? undefined : status, keyword: deferredKeyword }),
    placeholderData: keepPreviousData,
  });

  if (homeQuery.isLoading) return <LoadingRows rows={3} />;
  if (homeQuery.isError) return <ErrorState title="谷团详情加载失败" description={homeQuery.error.message} />;
  if (!homeQuery.data) return <EmptyState title="谷团不存在" description="后端没有返回该谷团。" />;

  const { group, capabilities, summary } = homeQuery.data;

  return (
    <div className="space-y-5">
      <PageHeader
        title={group.name}
        description={group.description || "谷团详情默认显示当前正在进行中的拼谷。"}
        action={
          <>
            {capabilities.canCreateGroupBuy ? <Link to="/app/group-buys/new" className="btn btn-primary"><Plus className="size-4" />新建拼团</Link> : null}
            {capabilities.canEnterAdmin ? <Link to="/app/groups/$groupId/admin" params={{ groupId }} className="btn btn-secondary"><Settings className="size-4" />管理台</Link> : null}
          </>
        }
      />

      <Surface className="p-5">
        <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
          <div>
            <div className="flex items-center gap-3">
              <div className="flex size-16 items-center justify-center rounded-lg bg-cyan-50 text-2xl font-semibold text-cyan-800">
                {group.name.slice(0, 1)}
              </div>
              <div>
                <div className="text-sm text-slate-500">团长 / 维护人</div>
                <div className="font-semibold text-slate-950">{group.leader.displayName}</div>
              </div>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <StatBlock label="成员" value={group.memberCount} />
            <StatBlock label="进行中" value={summary.activeGroupBuyCount} />
            <StatBlock label="待付款" value={summary.myPendingPaymentCount} />
          </div>
        </div>
      </Surface>

      {capabilities.canEnterAdmin ? (
        <Surface className="flex flex-col gap-3 border-cyan-200 bg-cyan-50 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="font-semibold text-cyan-950">工作台</div>
            <p className="text-sm text-cyan-800">管理拼团、付款、转运、排发等流程。</p>
          </div>
          <Link to="/app/groups/$groupId/admin" params={{ groupId }} className="btn btn-primary">立即进入</Link>
        </Surface>
      ) : null}

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="w-full lg:max-w-lg">
          <SearchBox value={keyword} onChange={setKeyword} placeholder="搜索活动名或类型" />
        </div>
        <div className="flex gap-2 overflow-x-auto">
          {statusFilters.map((item) => (
            <button
              key={item}
              className={item === status ? "btn btn-primary" : "btn btn-secondary"}
              onClick={() => setStatus(item)}
              type="button"
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      {buysQuery.isLoading ? <LoadingRows rows={3} /> : null}
      {buysQuery.isError ? <ErrorState title="拼团列表加载失败" description={buysQuery.error.message} /> : null}
      {buysQuery.data?.items.length === 0 ? <EmptyState title="暂无拼团" description="当前筛选下没有拼团。" /> : null}
      <DataGrid>
        {buysQuery.data?.items.map((item) => (
          <Link key={item.id} to="/app/group-buys/$groupBuyId" params={{ groupBuyId: item.id }}>
            <Surface className="overflow-hidden hover:border-cyan-300">
              <div className="flex aspect-[16/8] items-center justify-center bg-slate-100 text-4xl font-semibold text-cyan-800">
                {item.title.slice(0, 1)}
              </div>
              <div className="p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge value={item.status} />
                  <span className="badge-neutral">{item.type}</span>
                </div>
                <h3 className="mt-3 text-base font-semibold text-slate-950">{item.title}</h3>
                <p className="mt-2 text-sm text-slate-500">发起人 {item.initiator?.displayName || item.ownerName || "未返回"} · 截团 {formatDateTime(item.closeAt)}</p>
                <div className="mt-4 grid grid-cols-3 gap-2">
                  <StatBlock label="商品" value={item.itemCount} />
                  <StatBlock label="可拼" value={item.availableQuantity} />
                  <StatBlock label="我参与" value={item.myRecordCount} />
                </div>
              </div>
            </Surface>
          </Link>
        ))}
      </DataGrid>
    </div>
  );
}
