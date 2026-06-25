import { useQuery } from "@tanstack/react-query";

import { api, ApiError } from "@/lib/api";
import { ErrorState, InterfacePending, LoadingRows, PageHeader, Surface } from "@/components/ui";

export function AdminUsersPage() {
  const query = useQuery({ queryKey: ["users"], queryFn: () => api.getUsers() });
  return (
    <div className="space-y-5">
      <PageHeader title="用户与角色管理" description="管理展示名、QQ 号、群昵称、角色和账号状态。" />
      {query.isLoading ? <LoadingRows rows={3} /> : null}
      {query.error instanceof ApiError && query.error.status === 404 ? <InterfacePending endpoint="GET /api/users / PATCH /api/users/{userId}" description="后端需要提供用户列表接口；已有文档中管理员更新用户身份接口也需要挂载。" /> : null}
      {query.isError && !(query.error instanceof ApiError && query.error.status === 404) ? <ErrorState title="加载失败" description={query.error.message} /> : null}
      {query.data ? <Surface className="p-4"><pre className="overflow-auto text-xs">{JSON.stringify(query.data, null, 2)}</pre></Surface> : null}
    </div>
  );
}
