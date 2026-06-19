import { startTransition } from "react";
import { Link, Navigate, useNavigate } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { ArrowRight } from "lucide-react";
import { z } from "zod";

import { authStore, useAuthState } from "@/lib/auth-store";
import { runtimeModeLabel } from "@/lib/runtime";
import { Button, Field, Panel, TextInput } from "@/components/ui";

const loginSchema = z.object({
  account: z.string().trim().min(1, "请输入账号"),
  password: z.string().min(6, "密码至少 6 位"),
});

type LoginFormValues = z.infer<typeof loginSchema>;

const demoAccounts = [
  { account: "member", label: "普通成员" },
  { account: "maintainer", label: "拼单维护人" },
  { account: "stock", label: "囤货人" },
  { account: "admin", label: "管理员" },
];

export function LoginPage() {
  const auth = useAuthState();
  const navigate = useNavigate();

  const {
    register,
    handleSubmit,
    formState: { errors },
    setValue,
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      account: "member",
      password: "123456",
    },
  });

  const loginMutation = useMutation({
    mutationFn: (values: LoginFormValues) => authStore.login(values),
    onSuccess: () => {
      startTransition(() => {
        void navigate({ to: "/app/groups", replace: true });
      });
    },
  });

  if (auth.status === "authenticated") {
    return <Navigate to="/app/groups" replace />;
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="grid w-full max-w-5xl gap-6 lg:grid-cols-[1.05fr_0.95fr]">
        <Panel className="overflow-hidden p-7 lg:p-9" strong>
          <div className="text-xs font-semibold uppercase tracking-[0.28em] text-[var(--accent)]">
            RibSys
          </div>
          <h1 className="mt-3 text-4xl font-semibold tracking-tight text-slate-900">
            先把核心业务链路跑起来
          </h1>
          <p className="mt-4 max-w-xl text-sm leading-7 text-slate-600">
            当前版本优先打通登录、谷团、拼团详情和管理入口。还没完全定稿的页面先保持轻量，
            但角色差异、状态标签和响应式结构已经预留好了。
          </p>

          <div className="mt-8 grid gap-3 sm:grid-cols-2">
            {demoAccounts.map((item) => (
              <button
                key={item.account}
                type="button"
                className="rounded-[24px] border border-white/80 bg-white/78 p-4 text-left transition hover:bg-white"
                onClick={() => {
                  setValue("account", item.account, { shouldValidate: true });
                  setValue("password", "123456", { shouldValidate: true });
                }}
              >
                <div className="text-sm font-semibold text-slate-900">{item.label}</div>
                <div className="mt-1 text-xs text-slate-500">
                  账号 {item.account} / 密码 123456
                </div>
              </button>
            ))}
          </div>
        </Panel>

        <Panel className="p-6 lg:p-8">
          <div className="space-y-2">
            <h2 className="text-2xl font-semibold text-slate-900">登录系统</h2>
            <p className="text-sm text-slate-600">
              当前接入的是 {runtimeModeLabel}。开发种子账号支持快速切换
              member / maintainer / stock / admin 四种角色，默认密码统一为 123456。
            </p>
          </div>

          <form
            className="mt-6 space-y-4"
            onSubmit={handleSubmit((values) => loginMutation.mutate(values))}
          >
            <Field label="账号 / QQ 号" error={errors.account?.message}>
              <TextInput placeholder="例如 member" {...register("account")} />
            </Field>

            <Field label="密码" error={errors.password?.message}>
              <TextInput type="password" placeholder="请输入密码" {...register("password")} />
            </Field>

            {loginMutation.error ? (
              <p className="text-sm text-rose-600">{loginMutation.error.message}</p>
            ) : null}

            <Button className="w-full" busy={loginMutation.isPending} type="submit">
              登录并进入谷团
              <ArrowRight className="size-4" />
            </Button>
          </form>

          <div className="mt-6 flex items-center justify-between gap-4 text-sm text-slate-500">
            <span>还没有账号？</span>
            <Link to="/register" className="font-semibold text-[var(--blue)]">
              注册 / 申请加入
            </Link>
          </div>
        </Panel>
      </div>
    </div>
  );
}
