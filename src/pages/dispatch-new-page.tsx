import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";

import { api } from "@/lib/api";
import { Button, ErrorState, Field, PageHeader, Surface, TextArea, TextInput } from "@/components/ui";

export function DispatchNewPage() {
  const form = useForm({
    defaultValues: {
      stockItemIds: "",
      receiverName: "",
      receiverPhone: "",
      receiverAddress: "",
      note: "",
    },
  });
  const mutation = useMutation({
    mutationFn: (values: Record<string, string>) =>
      api.createDispatchRequest({
        items: values.stockItemIds.split(",").map((id) => ({ stockItemId: id.trim(), quantity: 1 })),
        receiverName: values.receiverName,
        receiverPhone: values.receiverPhone,
        receiverAddress: values.receiverAddress,
        note: values.note,
      }),
  });

  return (
    <div className="space-y-5">
      <PageHeader title="创建排发申请" description="确认商品并填写收货人、电话、地址和备注。" />
      <Surface className="p-5">
        <form className="grid gap-4 lg:grid-cols-2" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
          <Field label="StockItem IDs" hint="逗号分隔"><TextInput {...form.register("stockItemIds")} /></Field>
          <Field label="收货人"><TextInput {...form.register("receiverName")} /></Field>
          <Field label="手机号"><TextInput {...form.register("receiverPhone")} /></Field>
          <Field label="国内地址"><TextInput {...form.register("receiverAddress")} /></Field>
          <Field label="备注"><TextArea {...form.register("note")} /></Field>
          {mutation.error ? <ErrorState title="提交失败" description={mutation.error.message} /> : null}
          {mutation.isSuccess ? <div className="rounded-lg bg-emerald-50 p-4 text-sm text-emerald-700">已提交到后端。</div> : null}
          <div className="lg:col-span-2"><Button busy={mutation.isPending} type="submit">提交排发申请</Button></div>
        </form>
      </Surface>
    </div>
  );
}
