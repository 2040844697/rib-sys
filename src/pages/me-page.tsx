import { useEffect } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { LogOut } from "lucide-react";

import { Button, ErrorState, Field, Panel, RoleBadge, SectionHeading, TextInput } from "@/components/ui";
import { api } from "@/lib/api";
import { authStore } from "@/lib/auth-store";

const meSchema = z.object({
  displayName: z.string().trim().min(2, "请填写展示名"),
  groupNickname: z.string().trim().min(2, "请填写群昵称"),
});

type MeFormValues = z.infer<typeof meSchema>;

export function MePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: () => api.getMe(),
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<MeFormValues>({
    resolver: zodResolver(meSchema),
    defaultValues: {
      displayName: "",
      groupNickname: "",
    },
  });

  useEffect(() => {
    if (!meQuery.data) {
      return;
    }

    reset({
      displayName: meQuery.data.displayName,
      groupNickname: meQuery.data.groupNickname,
    });
  }, [meQuery.data, reset]);

  const updateMutation = useMutation({
    mutationFn: api.updateMe,
    onSuccess: (_, values) => {
      authStore.updateUser(values);
      void queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });

  const logoutMutation = useMutation({
    mutationFn: async () => {
      await authStore.logout();
      queryClient.clear();
    },
    onSuccess: () => {
      void navigate({ to: "/login", replace: true });
    },
  });

  if (meQuery.isLoading) {
    return (
      <Panel className="p-6">
        <div className="animate-pulse space-y-3">
          <div className="h-6 w-40 rounded-full bg-slate-200" />
          <div className="h-4 w-full rounded-full bg-slate-200" />
          <div className="h-4 w-2/3 rounded-full bg-slate-200" />
        </div>
      </Panel>
    );
  }

  if (meQuery.isError || !meQuery.data) {
    return (
      <ErrorState
        title="个人信息加载失败"
        description={meQuery.isError ? meQuery.error.message : "暂无数据"}
      />
    );
  }

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Profile"
        title="我的资料"
        description="第一版先聚焦展示名、群昵称、角色和退出登录，后续再加更多账号状态信息。"
      />

      <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
        <Panel className="p-6" strong>
          <div className="space-y-3">
            <div className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--accent)]">
              当前账号
            </div>
            <div className="text-2xl font-semibold text-slate-900">
              {meQuery.data.displayName}
            </div>
            <div className="text-sm text-slate-500">QQ {meQuery.data.qqNumber}</div>
            <div className="text-sm text-slate-500">群昵称 {meQuery.data.groupNickname}</div>
          </div>

          <div className="mt-6 flex flex-wrap gap-2">
            {meQuery.data.roles.map((role) => (
              <RoleBadge key={role} role={role} />
            ))}
          </div>

          <div className="mt-6 rounded-[22px] bg-slate-50 p-4 text-sm text-slate-600">
            后续这里可以补账号状态、审批结果、默认谷团和常用提醒。
          </div>
        </Panel>

        <Panel className="p-6">
          <form
            className="space-y-4"
            onSubmit={handleSubmit((values) => updateMutation.mutate(values))}
          >
            <Field label="展示名" error={errors.displayName?.message}>
              <TextInput {...register("displayName")} />
            </Field>

            <Field label="群昵称" error={errors.groupNickname?.message}>
              <TextInput {...register("groupNickname")} />
            </Field>

            {updateMutation.error ? (
              <p className="text-sm text-rose-600">{updateMutation.error.message}</p>
            ) : null}

            <div className="flex flex-wrap gap-3">
              <Button busy={updateMutation.isPending} type="submit">
                保存修改
              </Button>
              <Button
                variant="secondary"
                busy={logoutMutation.isPending}
                type="button"
                onClick={() => logoutMutation.mutate()}
              >
                <LogOut className="size-4" />
                退出登录
              </Button>
            </div>
          </form>
        </Panel>
      </div>
    </div>
  );
}
