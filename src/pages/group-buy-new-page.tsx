import { useEffect } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import {
  Button,
  EmptyState,
  ErrorState,
  Field,
  Panel,
  SectionHeading,
  SelectInput,
  TextArea,
  TextInput,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAuthState } from "@/lib/auth-store";
import { hasAnyRole } from "@/lib/utils";

const createGroupBuySchema = z.object({
  groupId: z.string().min(1, "请选择所属谷团"),
  type: z.string().min(1, "请选择拼团类型"),
  title: z.string().trim().min(2, "请填写拼团标题"),
  description: z.string().trim().min(4, "请补充拼团说明"),
  closeAt: z.string().min(1, "请选择截团时间"),
  defaultChannel: z.string().trim().min(1, "请填写默认收款渠道"),
  defaultStockKeeper: z.string().trim().min(1, "请填写默认囤货人"),
});

type CreateGroupBuyValues = z.infer<typeof createGroupBuySchema>;

export function GroupBuyNewPage() {
  const navigate = useNavigate();
  const auth = useAuthState();
  const canCreate = hasAnyRole(auth.user?.roles ?? [], [
    "group_buy_maintainer",
    "admin",
  ]);

  const groupsQuery = useQuery({
    queryKey: ["groups"],
    queryFn: () => api.getGroups(),
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CreateGroupBuyValues>({
    resolver: zodResolver(createGroupBuySchema),
    defaultValues: {
      groupId: "",
      type: "群内开谷",
      title: "",
      description: "",
      closeAt: "2026-07-01T20:00",
      defaultChannel: "QQ 支付",
      defaultStockKeeper: auth.user?.displayName ?? "",
    },
  });

  useEffect(() => {
    const firstGroup = groupsQuery.data?.items[0];
    if (!firstGroup) {
      return;
    }

    reset((current) => ({
      ...current,
      groupId: current.groupId || firstGroup.id,
      defaultStockKeeper: current.defaultStockKeeper || auth.user?.displayName || "",
    }));
  }, [auth.user?.displayName, groupsQuery.data, reset]);

  const createMutation = useMutation({
    mutationFn: api.createGroupBuy,
    onSuccess: (result) => {
      void navigate({
        to: "/app/group-buys/$groupBuyId",
        params: { groupBuyId: result.groupBuyId },
      });
    },
  });

  if (!canCreate) {
    return (
      <ErrorState
        title="当前角色暂无创建权限"
        description="第一版按文档只向拼单维护人和管理员开放新建拼团。"
      />
    );
  }

  if (groupsQuery.isLoading) {
    return (
      <Panel className="p-6">
        <div className="animate-pulse space-y-3">
          <div className="h-6 w-40 rounded-full bg-slate-200" />
          <div className="h-4 w-full rounded-full bg-slate-200" />
          <div className="h-4 w-2/3 rounded-full bg-slate-200" />
        </div>
      </Panel>
    );
  }

  if (groupsQuery.isError) {
    return (
      <ErrorState
        title="无法读取谷团列表"
        description={groupsQuery.error.message}
      />
    );
  }

  if (!groupsQuery.data || groupsQuery.data.items.length === 0) {
    return (
      <EmptyState
        title="暂无可用谷团"
        description="先补齐谷团数据后，再继续创建拼团。"
      />
    );
  }

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Create"
        title="新建拼团"
        description="这页先把基础字段和保存动作做出来，商品图鉴与条目编辑后续再补。"
      />

      <Panel className="p-6 lg:p-8" strong>
        <form
          className="grid gap-4 lg:grid-cols-2"
          onSubmit={handleSubmit((values) => createMutation.mutate(values))}
        >
          <Field label="所属谷团" error={errors.groupId?.message}>
            <SelectInput {...register("groupId")}>
              {groupsQuery.data.items.map((group) => (
                <option key={group.id} value={group.id}>
                  {group.name}
                </option>
              ))}
            </SelectInput>
          </Field>

          <Field label="拼团类型" error={errors.type?.message}>
            <SelectInput {...register("type")}>
              <option value="群内开谷">群内开谷</option>
              <option value="补款">补款</option>
              <option value="补寄">补寄</option>
              <option value="现货加开">现货加开</option>
            </SelectInput>
          </Field>

          <Field label="拼团标题" error={errors.title?.message}>
            <TextInput placeholder="例如 月岛生日吧唧团" {...register("title")} />
          </Field>

          <Field label="截团时间" error={errors.closeAt?.message}>
            <TextInput type="datetime-local" {...register("closeAt")} />
          </Field>

          <Field label="默认收款渠道" error={errors.defaultChannel?.message}>
            <TextInput placeholder="例如 QQ 支付" {...register("defaultChannel")} />
          </Field>

          <Field label="默认囤货人" error={errors.defaultStockKeeper?.message}>
            <TextInput placeholder="填写负责囤货的成员" {...register("defaultStockKeeper")} />
          </Field>

          <Field label="拼团说明" error={errors.description?.message}>
            <TextArea placeholder="补充本次拼团说明、时间节点和注意事项" {...register("description")} />
          </Field>

          <div className="rounded-[24px] bg-slate-50 p-5 text-sm leading-7 text-slate-600">
            商品图鉴、拼团商品条目和库存快照将在下一轮接入。当前版本先完成：
            基础信息录入、保存、跳转到详情页，以及后续扩展所需的字段结构。
          </div>

          {createMutation.error ? (
            <p className="text-sm text-rose-600 lg:col-span-2">
              {createMutation.error.message}
            </p>
          ) : null}

          <div className="flex flex-wrap gap-3 lg:col-span-2">
            <Button busy={createMutation.isPending} type="submit">
              保存并进入详情
            </Button>
            <button
              type="button"
              className="button-secondary"
              onClick={() => reset()}
            >
              重置表单
            </button>
          </div>
        </form>
      </Panel>
    </div>
  );
}
