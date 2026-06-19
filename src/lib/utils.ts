import type { UserRole } from "@/types";

export function cn(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

export function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatShortDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "numeric",
    day: "numeric",
  }).format(new Date(value));
}

const roleLabels: Record<UserRole, string> = {
  member: "普通成员",
  group_buy_maintainer: "拼单维护人",
  stock_keeper: "囤货人",
  admin: "管理员",
};

export function formatRole(role: UserRole) {
  return roleLabels[role];
}

export function hasAnyRole(
  roles: UserRole[],
  expected: UserRole | UserRole[],
): boolean {
  const values = Array.isArray(expected) ? expected : [expected];
  return values.some((item) => roles.includes(item));
}
