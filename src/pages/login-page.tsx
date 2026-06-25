import { startTransition } from "react";
import { Link, Navigate, useNavigate } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { ArrowRight } from "lucide-react";
import { z } from "zod";

import { Button, Field, Surface, TextInput } from "@/components/ui";
import { authStore, useAuthState } from "@/lib/auth-store";

const schema = z.object({
  account: z.string().trim().min(1, "请输入账号"),
  password: z.string().min(1, "请输入密码"),
});

type FormValues = z.infer<typeof schema>;

const demoAccounts = ["member", "maintainer", "stock", "admin"];

export function LoginPage() {
  const auth = useAuthState();
  const navigate = useNavigate();
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { account: "", password: "" },
  });

  const mutation = useMutation({
    mutationFn: (values: FormValues) => authStore.login(values),
    onSuccess: () => {
      startTransition(() => {
        void navigate({ to: "/app/groups", replace: true });
      });
    },
  });

  if (auth.status === "authenticated") return <Navigate to="/app/groups" replace />;

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-4">
      <div className="grid w-full max-w-5xl gap-5 lg:grid-cols-[1fr_420px]">
        <Surface className="p-8">
          <div className="text-sm font-semibold text-cyan-700">RibSys</div>
          <h1 className="mt-3 text-4xl font-semibold tracking-tight text-slate-950">
            拼团流程工作台
          </h1>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-600">
            登录后进入移动端优先的 App 样式主界面，底部保留首页、谷团、我的。所有业务数据通过后端 API 读取。
          </p>
          <div className="mt-8 grid gap-3 sm:grid-cols-2">
            {demoAccounts.map((account) => (
              <button
                key={account}
                type="button"
                className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-left text-sm hover:bg-white"
                onClick={() => {
                  form.setValue("account", account, { shouldValidate: true });
                  form.setValue("password", "123456", { shouldValidate: true });
                }}
              >
                <div className="font-semibold text-slate-900">{account}</div>
                <div className="mt-1 text-xs text-slate-500">开发种子账号，密码 123456</div>
              </button>
            ))}
          </div>
        </Surface>

        <Surface className="p-6">
          <h2 className="text-xl font-semibold text-slate-950">登录</h2>
          <form className="mt-5 space-y-4" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
            <Field label="账号 / QQ 号" error={form.formState.errors.account?.message}>
              <TextInput {...form.register("account")} placeholder="请输入账号" />
            </Field>
            <Field label="密码" error={form.formState.errors.password?.message}>
              <TextInput {...form.register("password")} type="password" placeholder="请输入密码" />
            </Field>
            {mutation.error ? <p className="text-sm text-rose-600">{mutation.error.message}</p> : null}
            <Button className="w-full" busy={mutation.isPending} type="submit">
              登录
              <ArrowRight className="size-4" />
            </Button>
          </form>
          <div className="mt-5 flex items-center justify-between text-sm">
            <span className="text-slate-500">还没有账号？</span>
            <Link to="/register" className="font-semibold text-cyan-700">注册 / 申请加入</Link>
          </div>
        </Surface>
      </div>
    </div>
  );
}
