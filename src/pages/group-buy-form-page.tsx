import { useEffect } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { useForm } from "react-hook-form";

import { api } from "@/lib/api";
import { Button, ErrorState, Field, LoadingRows, PageHeader, SelectInput, Surface, TextArea, TextInput } from "@/components/ui";

interface FormValues {
  groupId: string;
  type: string;
  title: string;
  description: string;
  closeAt: string;
  paymentChannelId: string;
}

export function GroupBuyFormPage() {
  const params = useParams({ strict: false }) as { groupBuyId?: string };
  const groupBuyId = params.groupBuyId;
  const navigate = useNavigate();
  const groupsQuery = useQuery({ queryKey: ["groups"], queryFn: () => api.getGroups() });
  const detailQuery = useQuery({
    queryKey: ["group-buy-detail", groupBuyId],
    queryFn: () => api.getGroupBuyDetail(groupBuyId || ""),
    enabled: Boolean(groupBuyId),
  });
  const form = useForm<FormValues>({
    defaultValues: {
      groupId: "",
      type: "群内开谷",
      title: "",
      description: "",
      closeAt: "2026-07-01T20:00",
      paymentChannelId: "",
    },
  });

  useEffect(() => {
    const firstGroup = groupsQuery.data?.items[0];
    if (firstGroup && !form.getValues("groupId")) form.setValue("groupId", firstGroup.id);
  }, [form, groupsQuery.data]);

  useEffect(() => {
    if (!detailQuery.data) return;
    form.reset({
      groupId: detailQuery.data.groupBuy.groupId,
      type: detailQuery.data.groupBuy.type,
      title: detailQuery.data.groupBuy.title,
      description: detailQuery.data.groupBuy.description || "",
      closeAt: detailQuery.data.groupBuy.closeAt.slice(0, 16),
      paymentChannelId: detailQuery.data.groupBuy.paymentChannelId || "",
    });
  }, [detailQuery.data, form]);

  const save = useMutation<{ groupBuyId?: string; ok?: true }, Error, FormValues>({
    mutationFn: (values: FormValues) =>
      groupBuyId ? api.updateGroupBuy(groupBuyId, values) : api.createGroupBuy(values),
    onSuccess: (result) => {
      const nextId =
        groupBuyId ||
        ("groupBuyId" in result && typeof result.groupBuyId === "string"
          ? result.groupBuyId
          : undefined);
      if (nextId) void navigate({ to: "/app/group-buys/$groupBuyId", params: { groupBuyId: nextId } });
    },
  });

  if (groupsQuery.isLoading || detailQuery.isLoading) return <LoadingRows rows={2} />;
  if (groupsQuery.isError) return <ErrorState title="无法读取谷团" description={groupsQuery.error.message} />;
  if (detailQuery.isError) return <ErrorState title="无法读取拼团" description={detailQuery.error.message} />;

  return (
    <div className="space-y-5">
      <PageHeader
        title={groupBuyId ? "编辑拼团" : "新建拼团"}
        description="基础信息、收款方式、商品和库存都在这个页面完成。商品条目使用后端拼团商品接口逐步接入。"
        action={<Link to="/app/goods" className="btn btn-secondary">打开商品图鉴</Link>}
      />
      <Surface className="p-5">
        <form className="grid gap-4 lg:grid-cols-2" onSubmit={form.handleSubmit((values) => save.mutate(values))}>
          <Field label="所属谷团">
            <SelectInput {...form.register("groupId")}>
              {groupsQuery.data?.items.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
            </SelectInput>
          </Field>
          <Field label="拼团类型">
            <SelectInput {...form.register("type")}>
              <option>群内开谷</option>
              <option>补款</option>
              <option>现货加开</option>
              <option>补寄</option>
            </SelectInput>
          </Field>
          <Field label="标题"><TextInput {...form.register("title", { required: true })} /></Field>
          <Field label="截团时间"><TextInput type="datetime-local" {...form.register("closeAt")} /></Field>
          <Field label="收款方式 ID"><TextInput {...form.register("paymentChannelId")} placeholder="选择已有收款方式后填入" /></Field>
          <div className="flex items-end"><Link to="/app/me/payment-channels" className="btn btn-secondary">管理/新建收款方式</Link></div>
          <Field label="说明"><TextArea {...form.register("description")} /></Field>
          <Surface className="p-4">
            <h3 className="font-semibold text-slate-950">商品与库存</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">保存拼团后，可通过 `/api/group-buy-items` 创建商品、库存和内定库存。后续可继续把这里做成可编辑表格。</p>
          </Surface>
          {save.error ? <p className="text-sm text-rose-600 lg:col-span-2">{save.error.message}</p> : null}
          <div className="flex gap-2 lg:col-span-2">
            <Button busy={save.isPending} type="submit">保存</Button>
            <Button type="button" variant="secondary" onClick={() => form.reset()}>重置</Button>
          </div>
        </form>
      </Surface>
    </div>
  );
}
