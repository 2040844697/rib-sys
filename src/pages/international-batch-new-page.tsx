import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";

import { api } from "@/lib/api";
import { Button, ErrorState, Field, PageHeader, Surface, TextArea, TextInput } from "@/components/ui";

export function InternationalBatchNewPage() {
  const form = useForm({ defaultValues: { amountCny: "", groupBuyIds: "", note: "" } });
  const mutation = useMutation({
    mutationFn: (values: Record<string, string>) =>
      api.createInternationalBatch({
        amountCny: values.amountCny,
        groupBuyIds: values.groupBuyIds.split(",").map((id) => id.trim()).filter(Boolean),
        note: values.note,
      }),
  });

  return (
    <div className="space-y-5">
      <PageHeader title="国际转运添加页" description="第一版必填：金额，以及关联哪些拼单。" />
      <Surface className="p-5">
        <form className="grid gap-4 lg:grid-cols-2" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
          <Field label="金额"><TextInput {...form.register("amountCny")} /></Field>
          <Field label="关联拼单 IDs"><TextInput {...form.register("groupBuyIds")} placeholder="逗号分隔" /></Field>
          <Field label="备注"><TextArea {...form.register("note")} /></Field>
          {mutation.error ? <ErrorState title="创建失败" description={mutation.error.message} /> : null}
          {mutation.isSuccess ? <div className="rounded-lg bg-emerald-50 p-4 text-sm text-emerald-700">后端已接收。</div> : null}
          <div className="lg:col-span-2"><Button busy={mutation.isPending} type="submit">创建批次</Button></div>
        </form>
      </Surface>
    </div>
  );
}
