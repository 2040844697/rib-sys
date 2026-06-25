import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";

import { api, ApiError } from "@/lib/api";
import { Button, ErrorState, Field, InterfacePending, LoadingRows, PageHeader, Surface, TextInput } from "@/components/ui";

export function AddressesPage() {
  const query = useQuery({ queryKey: ["addresses"], queryFn: () => api.getAddresses() });
  const form = useForm({ defaultValues: { receiverName: "", receiverPhone: "", receiverAddress: "" } });
  const create = useMutation({ mutationFn: (values: Record<string, string>) => api.createAddress(values) });

  return (
    <div className="space-y-5">
      <PageHeader title="地址簿" description="排发申请保存地址快照，地址簿用于快速填充。" />
      {query.isLoading ? <LoadingRows rows={2} /> : null}
      {query.error instanceof ApiError && query.error.status === 404 ? <InterfacePending endpoint="GET /api/me/addresses / POST /api/me/addresses" description="后端需要提供当前用户地址簿查询和创建接口。" /> : null}
      {query.isError && !(query.error instanceof ApiError && query.error.status === 404) ? <ErrorState title="加载失败" description={query.error.message} /> : null}
      {query.data ? <Surface className="p-4"><pre className="overflow-auto text-xs">{JSON.stringify(query.data, null, 2)}</pre></Surface> : null}
      <Surface className="p-5">
        <form className="grid gap-4 lg:grid-cols-3" onSubmit={form.handleSubmit((values) => create.mutate(values))}>
          <Field label="收货人"><TextInput {...form.register("receiverName")} /></Field>
          <Field label="手机号"><TextInput {...form.register("receiverPhone")} /></Field>
          <Field label="地址"><TextInput {...form.register("receiverAddress")} /></Field>
          {create.error ? <p className="text-sm text-rose-600 lg:col-span-3">{create.error.message}</p> : null}
          <div className="lg:col-span-3"><Button busy={create.isPending} type="submit">新增地址</Button></div>
        </form>
      </Surface>
    </div>
  );
}
