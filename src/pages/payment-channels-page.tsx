import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";

import { api, ApiError } from "@/lib/api";
import { Button, ErrorState, Field, InterfacePending, LoadingRows, PageHeader, SelectInput, Surface, TextArea, TextInput } from "@/components/ui";

export function PaymentChannelsPage() {
  const query = useQuery({ queryKey: ["payment-channels"], queryFn: () => api.getPaymentChannels() });
  const form = useForm({ defaultValues: { type: "QQ", displayName: "", accountText: "", note: "" } });
  const create = useMutation({ mutationFn: (values: Record<string, string>) => api.createPaymentChannel(values) });

  return (
    <div className="space-y-5">
      <PageHeader title="收款方式" description="从我的页进入；新建拼团时选择已有收款方式，也可快速新建。" />
      {query.isLoading ? <LoadingRows rows={2} /> : null}
      {query.error instanceof ApiError && query.error.status === 404 ? <InterfacePending endpoint="GET /api/payment-channels / POST /api/payment-channels" description="后端需要挂载收款方式列表和创建接口。" /> : null}
      {query.isError && !(query.error instanceof ApiError && query.error.status === 404) ? <ErrorState title="加载失败" description={query.error.message} /> : null}
      {query.data ? <Surface className="p-4"><pre className="overflow-auto text-xs">{JSON.stringify(query.data, null, 2)}</pre></Surface> : null}
      <Surface className="p-5">
        <form className="grid gap-4 lg:grid-cols-2" onSubmit={form.handleSubmit((values) => create.mutate(values))}>
          <Field label="类型"><SelectInput {...form.register("type")}><option>QQ</option><option>支付宝</option><option>微信</option><option>银行卡</option></SelectInput></Field>
          <Field label="展示名"><TextInput {...form.register("displayName")} /></Field>
          <Field label="账号"><TextInput {...form.register("accountText")} /></Field>
          <Field label="说明"><TextArea {...form.register("note")} /></Field>
          {create.error ? <p className="text-sm text-rose-600 lg:col-span-2">{create.error.message}</p> : null}
          <div className="lg:col-span-2"><Button busy={create.isPending} type="submit">新建收款方式</Button></div>
        </form>
      </Surface>
    </div>
  );
}
