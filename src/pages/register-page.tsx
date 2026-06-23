import { useState } from "react";
import { Link, Navigate } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { api } from "@/lib/api";
import { useAuthState } from "@/lib/auth-store";
import type { RegisterResponse } from "@/types";
import { Button, Field, Panel, TextInput } from "@/components/ui";

const registerSchema = z
  .object({
    displayName: z.string().trim().min(2, "请填写展示名"),
    qqNumber: z.string().trim().min(5, "请填写 QQ 号"),
    groupNickname: z.string().trim().min(2, "请填写群昵称"),
    password: z.string().min(6, "密码至少 6 位"),
    confirmPassword: z.string().min(6, "请再次输入密码"),
  })
  .refine((value) => value.password === value.confirmPassword, {
    message: "两次输入的密码不一致",
    path: ["confirmPassword"],
  });

type RegisterFormValues = z.infer<typeof registerSchema>;

export function RegisterPage() {
  const auth = useAuthState();
  const [submittedResult, setSubmittedResult] = useState<{
    response: RegisterResponse;
    qqNumber: string;
  } | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      displayName: "",
      qqNumber: "",
      groupNickname: "",
      password: "",
      confirmPassword: "",
    },
  });

  const registerMutation = useMutation({
    mutationFn: (values: RegisterFormValues) => api.register(values),
    onSuccess: (response, values) => {
      setSubmittedResult({
        response,
        qqNumber: values.qqNumber,
      });
    },
  });

  if (auth.status === "authenticated") {
    return <Navigate to="/app/groups" replace />;
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <Panel className="w-full max-w-2xl p-6 lg:p-8" strong>
        <div className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--accent)]">
            加入 RibSys
          </div>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900">
            先做一个可提交的注册 / 申请页
          </h1>
          <p className="text-sm leading-7 text-slate-600">
            文档里提到这里后续可能会切成“申请加入”模式，所以当前实现优先保证字段结构和提交流程可用。
          </p>
        </div>

        {submittedResult ? (
          <div className="mt-6 rounded-[24px] bg-emerald-50 p-5 text-emerald-700">
            <div className="text-lg font-semibold">提交成功</div>
            <p className="mt-2 text-sm">
              {submittedResult.response.canLoginNow === false ||
              submittedResult.response.nextAction === "wait_review"
                ? "注册申请已提交，当前账号暂时还不能立即登录。后续如果后端切到审核模式，这里会继续沿用这一种提示。"
                : `账号已创建成功。你可以使用 QQ 号 ${submittedResult.qqNumber} 和刚设置的密码直接登录。`}
            </p>
          </div>
        ) : null}

        <form
          className="mt-6 grid gap-4 lg:grid-cols-2"
          onSubmit={handleSubmit((values) => registerMutation.mutate(values))}
        >
          <Field label="展示名" error={errors.displayName?.message}>
            <TextInput placeholder="例如 成员A" {...register("displayName")} />
          </Field>

          <Field label="QQ 号" error={errors.qqNumber?.message}>
            <TextInput placeholder="请输入 QQ 号" {...register("qqNumber")} />
          </Field>

          <Field label="群昵称" error={errors.groupNickname?.message}>
            <TextInput placeholder="例如 A昵称" {...register("groupNickname")} />
          </Field>

          <div />

          <Field label="密码" error={errors.password?.message}>
            <TextInput type="password" placeholder="请设置密码" {...register("password")} />
          </Field>

          <Field label="确认密码" error={errors.confirmPassword?.message}>
            <TextInput
              type="password"
              placeholder="请再次输入密码"
              {...register("confirmPassword")}
            />
          </Field>

          {registerMutation.error ? (
            <p className="text-sm text-rose-600 lg:col-span-2">
              {registerMutation.error.message}
            </p>
          ) : null}

          <div className="flex flex-wrap gap-3 lg:col-span-2">
            <Button busy={registerMutation.isPending} type="submit">
              提交注册
            </Button>
            <Link to="/login" className="button-secondary">
              返回登录
            </Link>
          </div>
        </form>
      </Panel>
    </div>
  );
}
