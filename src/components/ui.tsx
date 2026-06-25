import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import { AlertCircle, LoaderCircle, Search } from "lucide-react";

import { cn, formatRole } from "@/lib/utils";
import type { UserRole } from "@/types";

const statusStyles: Record<string, string> = {
  等待开团: "bg-slate-100 text-slate-700 ring-slate-200",
  拼拼拼: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  已切: "bg-sky-50 text-sky-700 ring-sky-200",
  已截团: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  已完成: "bg-teal-50 text-teal-700 ring-teal-200",
  已取消: "bg-zinc-100 text-zinc-600 ring-zinc-200",
  待付款: "bg-amber-50 text-amber-700 ring-amber-200",
  已提交: "bg-sky-50 text-sky-700 ring-sky-200",
  已确认: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  已驳回: "bg-rose-50 text-rose-700 ring-rose-200",
  未肾: "bg-amber-50 text-amber-700 ring-amber-200",
  未补国际: "bg-orange-50 text-orange-700 ring-orange-200",
  未到货: "bg-violet-50 text-violet-700 ring-violet-200",
  可排发: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  已申请排发: "bg-sky-50 text-sky-700 ring-sky-200",
  已排发: "bg-cyan-50 text-cyan-700 ring-cyan-200",
  异常: "bg-rose-50 text-rose-700 ring-rose-200",
};

export function Surface({
  children,
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("surface", className)} {...props}>
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-950">{title}</h1>
        {description ? <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">{description}</p> : null}
      </div>
      {action ? <div className="flex shrink-0 flex-wrap gap-2">{action}</div> : null}
    </div>
  );
}

export function Button({
  className,
  variant = "primary",
  busy = false,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "quiet" | "danger";
  busy?: boolean;
}) {
  return (
    <button
      className={cn(
        "btn",
        variant === "primary" && "btn-primary",
        variant === "secondary" && "btn-secondary",
        variant === "quiet" && "btn-quiet",
        variant === "danger" && "btn-danger",
        className,
      )}
      disabled={busy || props.disabled}
      {...props}
    >
      {busy ? <LoaderCircle className="size-4 animate-spin" /> : null}
      {children}
    </button>
  );
}

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <div className="mb-1.5 flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-slate-700">{label}</span>
        {hint ? <span className="text-xs text-slate-500">{hint}</span> : null}
      </div>
      {children}
      {error ? <p className="mt-1.5 text-sm text-rose-600">{error}</p> : null}
    </label>
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn("control", props.className)} {...props} />;
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn("control min-h-28", props.className)} {...props} />;
}

export function SelectInput(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn("control", props.className)} {...props} />;
}

export function SearchBox({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
      <TextInput
        className="pl-9"
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

export function StatusBadge({ value }: { value?: string | null }) {
  const label = value || "未知";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ring-1",
        statusStyles[label] ?? "bg-slate-100 text-slate-700 ring-slate-200",
      )}
    >
      {label}
    </span>
  );
}

export function RoleBadge({ role }: { role: UserRole }) {
  return <span className="badge-neutral">{formatRole(role)}</span>;
}

export function StatBlock({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-1 text-lg font-semibold text-slate-950">{value}</div>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <Surface className="p-8 text-center">
      <h3 className="text-base font-semibold text-slate-950">{title}</h3>
      <p className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-slate-600">{description}</p>
      {action ? <div className="mt-5 flex justify-center">{action}</div> : null}
    </Surface>
  );
}

export function ErrorState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-rose-200 bg-rose-50 p-5">
      <div className="flex gap-3">
        <AlertCircle className="mt-0.5 size-5 shrink-0 text-rose-600" />
        <div>
          <h3 className="font-semibold text-rose-900">{title}</h3>
          <p className="mt-1 text-sm leading-6 text-rose-700">{description}</p>
          {action ? <div className="mt-4">{action}</div> : null}
        </div>
      </div>
    </div>
  );
}

export function InterfacePending({
  endpoint,
  description,
}: {
  endpoint: string;
  description: string;
}) {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-5">
      <div className="text-sm font-semibold text-amber-900">后端接口待接入</div>
      <p className="mt-2 text-sm leading-6 text-amber-800">{description}</p>
      <code className="mt-3 block rounded-md bg-white/70 px-3 py-2 text-xs text-amber-900">
        {endpoint}
      </code>
    </div>
  );
}

export function LoadingRows({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="surface animate-pulse p-4">
          <div className="h-4 w-40 rounded bg-slate-200" />
          <div className="mt-3 h-3 w-full rounded bg-slate-200" />
          <div className="mt-2 h-3 w-2/3 rounded bg-slate-200" />
        </div>
      ))}
    </div>
  );
}

export function DataGrid({
  children,
  columns = "lg:grid-cols-2",
}: {
  children: ReactNode;
  columns?: string;
}) {
  return <div className={cn("grid gap-4", columns)}>{children}</div>;
}
