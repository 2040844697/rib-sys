import { useEffect } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { LogOut } from "lucide-react";

import { api } from "@/lib/api";
import { authStore } from "@/lib/auth-store";
import { Button, ErrorState, Field, LoadingRows, PageHeader, RoleBadge, Surface, TextInput } from "@/components/ui";

export function MePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["me"], queryFn: () => api.getMe() });
  const form = useForm({ defaultValues: { displayName: "", groupNickname: "" } });

  useEffect(() => {
    if (query.data) {
      form.reset({ displayName: query.data.displayName, groupNickname: query.data.groupNickname });
    }
  }, [form, query.data]);

  const update = useMutation({
    mutationFn: api.updateMe,
    onSuccess: (_, values) => {
      authStore.updateUser(values);
      queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });
  const logout = useMutation({
    mutationFn: () => authStore.logout(),
    onSuccess: () => {
      queryClient.clear();
      void navigate({ to: "/login", replace: true });
    },
  });

  if (query.isLoading) return <LoadingRows rows={2} />;
  if (query.isError || !query.data) return <ErrorState title="个人信息加载失败" description={query.isError ? query.error.message : "无数据"} />;

  const entries = [
    ["我的拼单", "/app/me/records"],
    ["我的费用", "/app/me/charges"],
    ["可排发商品", "/app/me/dispatchable-items"],
    ["收款方式", "/app/me/payment-channels"],
    ["地址簿", "/app/me/addresses"],
  ] as const;

  return (
    <div className="space-y-5">
      <PageHeader title="我的" description="个人资料和普通成员高频入口。" />
      <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
        <Surface className="p-5">
          <h2 className="font-semibold text-slate-950">{query.data.displayName}</h2>
          <p className="mt-1 text-sm text-slate-500">QQ {query.data.qqNumber} · {query.data.groupNickname}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {query.data.roles.map((role) => <RoleBadge key={role} role={role} />)}
          </div>
          <div className="mt-5 grid gap-2">
            {entries.map(([label, to]) => <Link key={to} to={to} className="btn btn-secondary justify-start">{label}</Link>)}
          </div>
        </Surface>
        <Surface className="p-5">
          <form className="space-y-4" onSubmit={form.handleSubmit((values) => update.mutate(values))}>
            <Field label="展示名"><TextInput {...form.register("displayName")} /></Field>
            <Field label="群昵称"><TextInput {...form.register("groupNickname")} /></Field>
            {update.error ? <p className="text-sm text-rose-600">{update.error.message}</p> : null}
            <div className="flex gap-2">
              <Button busy={update.isPending} type="submit">保存</Button>
              <Button variant="secondary" busy={logout.isPending} type="button" onClick={() => logout.mutate()}><LogOut className="size-4" />退出</Button>
            </div>
          </form>
        </Surface>
      </div>
    </div>
  );
}
