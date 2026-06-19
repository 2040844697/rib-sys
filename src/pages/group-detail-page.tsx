import { startTransition, useDeferredValue, useState } from "react";
import { Link, useParams } from "@tanstack/react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";

import {
  AdminEntryBar,
  GroupBuyCard,
  GroupHeaderCard,
} from "@/components/cards";
import {
  Button,
  CardSkeleton,
  EmptyState,
  ErrorState,
  FilterTabs,
  SearchField,
  SectionHeading,
} from "@/components/ui";
import { api } from "@/lib/api";

const filters = ["全部", "进行中", "未开始", "已截团", "已完成", "已取消"];

export function GroupDetailPage() {
  const { groupId } = useParams({ from: "/app/groups/$groupId" });
  const [status, setStatus] = useState("全部");
  const [keyword, setKeyword] = useState("");
  const deferredKeyword = useDeferredValue(keyword);

  const groupHomeQuery = useQuery({
    queryKey: ["group-home", groupId],
    queryFn: () => api.getGroupHome(groupId),
  });

  const groupBuysQuery = useQuery({
    queryKey: ["group-buys", groupId, status, deferredKeyword],
    queryFn: () =>
      api.getGroupBuys(groupId, {
        status: status === "全部" ? undefined : status,
        keyword: deferredKeyword || undefined,
      }),
    placeholderData: keepPreviousData,
  });

  const isInitialLoading =
    groupHomeQuery.isLoading || (groupBuysQuery.isLoading && !groupBuysQuery.data);

  if (isInitialLoading) {
    return (
      <div className="space-y-4">
        <CardSkeleton lines={5} />
        <CardSkeleton lines={4} />
        <CardSkeleton lines={4} />
      </div>
    );
  }

  if (groupHomeQuery.isError) {
    return (
      <ErrorState
        title="谷团详情加载失败"
        description={groupHomeQuery.error.message}
        action={
          <button className="button-secondary" onClick={() => groupHomeQuery.refetch()}>
            重试
          </button>
        }
      />
    );
  }

  if (!groupHomeQuery.data) {
    return (
      <EmptyState
        title="谷团不存在"
        description="这个谷团可能已经被移除，或者当前 mock 数据还没有补到这里。"
        action={<Link to="/app/groups" className="button-secondary">返回谷团列表</Link>}
      />
    );
  }

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Group Home"
        title={groupHomeQuery.data.group.name}
        description="顶部保留谷团信息卡片，中段是工作台入口，下方是状态筛选和拼团列表。"
        action={
          groupHomeQuery.data.capabilities.canCreateGroupBuy ? (
            <Link to="/app/group-buys/new" className="button-primary">
              <Plus className="size-4" />
              新建拼团
            </Link>
          ) : undefined
        }
      />

      <GroupHeaderCard data={groupHomeQuery.data} />

      {groupHomeQuery.data.capabilities.canEnterAdmin ? (
        <AdminEntryBar
          groupId={groupId}
          canCreateGroupBuy={groupHomeQuery.data.capabilities.canCreateGroupBuy}
        />
      ) : null}

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="w-full lg:max-w-lg">
          <SearchField
            value={keyword}
            onChange={setKeyword}
            placeholder="搜索拼团标题或类型"
          />
        </div>
        {groupBuysQuery.isFetching ? (
          <div className="text-sm text-slate-500">正在刷新列表...</div>
        ) : null}
      </div>

      <FilterTabs
        items={filters}
        value={status}
        onChange={(value) => startTransition(() => setStatus(value))}
      />

      {groupBuysQuery.isError ? (
        <ErrorState
          title="拼团列表加载失败"
          description={groupBuysQuery.error.message}
          action={
            <button className="button-secondary" onClick={() => groupBuysQuery.refetch()}>
              重试
            </button>
          }
        />
      ) : null}

      {groupBuysQuery.data && groupBuysQuery.data.items.length === 0 ? (
        <EmptyState
          title="暂无拼团"
          description="这里已经保留了搜索和状态筛选，后续直接接真实数据即可继续扩展。"
          action={
            groupHomeQuery.data.capabilities.canCreateGroupBuy ? (
              <Link to="/app/group-buys/new" className="button-secondary">
                <Plus className="size-4" />
                新建一个拼团
              </Link>
            ) : undefined
          }
        />
      ) : null}

      {groupBuysQuery.data && groupBuysQuery.data.items.length > 0 ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {groupBuysQuery.data.items.map((item) => (
            <GroupBuyCard key={item.id} item={item} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
