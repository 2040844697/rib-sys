import { useState } from "react";
import { Link, Navigate } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { api } from "@/lib/api";
import { useAuthState } from "@/lib/auth-store";
import { Button, Field, Surface, TextInput } from "@/components/ui";

const schema = z
  .object({
    displayName: z.string().trim().min(2, "请填写展示名"),
    qqNumber: z.string().trim().min(5, "请填写 QQ 号"),
    groupNickname: z.string().trim().min(2, "请填写群昵称"),
    password: z.string().min(6, "密码至少 6 位"),
    confirmPassword: z.string().min(6, "请再次输入密码"),
  })
  .refine((value) => value.password === value.confirmPassword, {
    message: "两次密码输入不一致",
    path: ["confirmPassword"],
  });

type FormValues = z.infer<typeof schema>;

export function RegisterPage() {
  const auth = useAuthState();
  const [done, setDone] = useState(false);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { displayName: "", qqNumber: "", groupNickname: "", password: "", confirmPassword: "" },
  });

  const mutation = useMutation({
    mutationFn: (values: FormValues) => api.register(values),
    onSuccess: () => setDone(true),
  });

  if (auth.status === "authenticated") return <Navigate to="/app/groups" replace />;

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-4">
      <Surface className="w-full max-w-2xl p-6">
        <h1 className="text-2xl font-semibold text-slate-950">注册 / 申请加入</h1>
        <p className="mt-2 text-sm text-slate-600">第一版以登录为主，这里承接注册或审核申请流程。</p>
        {done ? (
          <div className="mt-5 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
            提交成功。后端如果启用审核模式，账号会进入待审核；否则可以返回登录。
          </div>
        ) : null}
        <form className="mt-5 grid gap-4 sm:grid-cols-2" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
          <Field label="展示名" error={form.formState.errors.displayName?.message}>
            <TextInput {...form.register("displayName")} />
          </Field>
          <Field label="QQ 号" error={form.formState.errors.qqNumber?.message}>
            <TextInput {...form.register("qqNumber")} />
          </Field>
          <Field label="群昵称" error={form.formState.errors.groupNickname?.message}>
            <TextInput {...form.register("groupNickname")} />
          </Field>
          <div />
          <Field label="密码" error={form.formState.errors.password?.message}>
            <TextInput type="password" {...form.register("password")} />
          </Field>
          <Field label="确认密码" error={form.formState.errors.confirmPassword?.message}>
            <TextInput type="password" {...form.register("confirmPassword")} />
          </Field>
          {mutation.error ? <p className="text-sm text-rose-600 sm:col-span-2">{mutation.error.message}</p> : null}
          <div className="flex gap-2 sm:col-span-2">
            <Button busy={mutation.isPending} type="submit">提交</Button>
            <Link to="/login" className="btn btn-secondary">返回登录</Link>
          </div>
        </form>
      </Surface>
    </div>
  );
}
