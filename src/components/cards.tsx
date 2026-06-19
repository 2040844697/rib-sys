import { ChevronRight, Pencil, Plus, Shield, Users } from "lucide-react";
import { Link } from "@tanstack/react-router";

import { Button, Panel, RoleBadge, StatPill, StatusBadge } from "@/components/ui";
import { formatDateTime } from "@/lib/utils";
import type {
  GroupBuyListItem,
  GroupHomeResponse,
  GroupSummaryItem,
} from "@/types";

export function GroupCard({ group }: { group: GroupSummaryItem }) {
  return (
    <Link to="/app/groups/$groupId" params={{ groupId: group.id }} className="block">
      <Panel className="p-5 transition hover:-translate-y-0.5 hover:bg-white/95">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <div className="flex size-12 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-lg font-bold text-[var(--accent-strong)]">
                {group.name.slice(0, 1)}
              </div>
              <div>
                <h3 className="text-lg font-semibold text-slate-900">{group.name}</h3>
                <p className="text-sm text-slate-500">
                  进行中拼团 {group.activeGroupBuyCount} 个
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {group.myRoles.map((role) => (
                <RoleBadge key={role} role={role} />
              ))}
            </div>
          </div>
          <ChevronRight className="mt-1 size-5 text-slate-400" />
        </div>
        <div className="mt-5 grid grid-cols-2 gap-3">
          <StatPill label="成员人数" value={group.memberCount} />
          <StatPill label="活跃拼团" value={group.activeGroupBuyCount} accent="accent" />
        </div>
      </Panel>
    </Link>
  );
}

export function GroupHeaderCard({ data }: { data: GroupHomeResponse }) {
  const { group, summary, capabilities } = data;

  return (
    <Panel className="overflow-hidden p-6">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-4">
          <div className="flex items-center gap-4">
            <div className="flex size-14 items-center justify-center rounded-[22px] bg-[var(--accent-soft)] text-xl font-bold text-[var(--accent-strong)]">
              {group.name.slice(0, 1)}
            </div>
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--accent)]">
                谷团详情
              </div>
              <h2 className="text-2xl font-semibold text-slate-900">{group.name}</h2>
            </div>
          </div>
          <p className="max-w-2xl text-sm leading-6 text-slate-600">{group.description}</p>
          <div className="flex flex-wrap gap-2">
            {group.myRoles.map((role) => (
              <RoleBadge key={role} role={role} />
            ))}
          </div>
        </div>

        <div className="flex flex-wrap gap-2 lg:max-w-sm lg:justify-end">
          {capabilities.canEditGroup ? (
            <Button variant="secondary" className="px-3 py-2">
              <Pencil className="size-4" />
              编辑团信息
            </Button>
          ) : null}
          <div className="chip-muted">
            <Users className="size-4" />
            团长 {group.leader.displayName}
          </div>
        </div>
      </div>
      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        <StatPill label="成员" value={group.memberCount} />
        <StatPill label="进行中拼团" value={summary.activeGroupBuyCount} accent="accent" />
        <StatPill label="我的待付款" value={summary.myPendingPaymentCount} accent="teal" />
      </div>
    </Panel>
  );
}

export function AdminEntryBar({
  groupId,
  canCreateGroupBuy,
}: {
  groupId: string;
  canCreateGroupBuy: boolean;
}) {
  return (
    <Panel className="flex flex-col gap-4 border-[rgba(39,94,134,0.18)] bg-[rgba(229,240,248,0.92)] p-5 lg:flex-row lg:items-center lg:justify-between">
      <div className="space-y-1">
        <div className="inline-flex items-center gap-2 rounded-full bg-white/85 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--blue)]">
          <Shield className="size-4" />
          工作台
        </div>
        <h3 className="text-lg font-semibold text-slate-900">
          管理拼团、付款、转运、排发等
        </h3>
        <p className="text-sm text-slate-600">
          当前先做模块入口页，后续再细化到各业务工作面板。
        </p>
      </div>
      <div className="flex flex-wrap gap-3">
        {canCreateGroupBuy ? (
          <Link to="/app/group-buys/new" className="button-secondary">
            <Plus className="size-4" />
            新建拼团
          </Link>
        ) : null}
        <Link
          to="/app/groups/$groupId/admin"
          params={{ groupId }}
          className="button-primary"
        >
          立即进入
          <ChevronRight className="size-4" />
        </Link>
      </div>
    </Panel>
  );
}

export function GroupBuyCard({ item }: { item: GroupBuyListItem }) {
  return (
    <Link
      to="/app/group-buys/$groupBuyId"
      params={{ groupBuyId: item.id }}
      className="block"
    >
      <Panel className="p-5 transition hover:-translate-y-0.5 hover:bg-white/95">
        <div className="flex flex-col gap-4">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge value={item.status} />
                <span className="chip-muted">{item.type}</span>
              </div>
              <h3 className="text-lg font-semibold leading-7 text-slate-900">{item.title}</h3>
              <p className="text-sm text-slate-500">截团时间 {formatDateTime(item.closeAt)}</p>
            </div>
            <ChevronRight className="mt-1 size-5 text-slate-400" />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <StatPill label="商品数" value={item.itemCount} />
            <StatPill label="剩余可拼" value={item.availableQuantity} accent="accent" />
            <StatPill label="我已认领" value={item.myRecordCount} accent="teal" />
          </div>
        </div>
      </Panel>
    </Link>
  );
}
