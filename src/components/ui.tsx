import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import { LoaderCircle, Search } from "lucide-react";

import { cn, formatRole } from "@/lib/utils";
import type { UserRole } from "@/types";

const statusStyles: Record<string, string> = {
  等待开团: "bg-slate-200 text-slate-700",
  拼拼拼: "bg-emerald-100 text-emerald-700",
  已切: "bg-sky-100 text-sky-700",
  已截团: "bg-slate-300 text-slate-700",
  已完成: "bg-teal-100 text-teal-700",
  已取消: "bg-zinc-200 text-zinc-700",
  可拼: "bg-emerald-100 text-emerald-700",
  已满: "bg-rose-100 text-rose-700",
  未肾: "bg-amber-100 text-amber-700",
  未补国际: "bg-orange-100 text-orange-700",
  未到货: "bg-indigo-100 text-indigo-700",
  可排发: "bg-emerald-100 text-emerald-700",
  已申请排发: "bg-sky-100 text-sky-700",
  已排发: "bg-cyan-100 text-cyan-700",
  转单中: "bg-yellow-100 text-yellow-700",
  已完结: "bg-lime-100 text-lime-700",
};

export function Panel({
  children,
  className,
  strong = false,
  ...props
}: HTMLAttributes<HTMLDivElement> & { strong?: boolean }) {
  return (
    <div
      className={cn(strong ? "surface-panel-strong" : "surface-panel", className)}
      {...props}
    >
      {children}
    </div>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
      <div className="space-y-1">
        {eyebrow ? (
          <div className="text-xs font-semibold uppercase tracking-[0.28em] text-[var(--accent)]">
            {eyebrow}
          </div>
        ) : null}
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900 lg:text-3xl">
          {title}
        </h1>
        {description ? <p className="text-sm text-slate-600">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function StatusBadge({ value }: { value: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold",
        statusStyles[value] ?? "bg-slate-100 text-slate-700",
      )}
    >
      {value}
    </span>
  );
}

export function RoleBadge({ role }: { role: UserRole }) {
  return (
    <span className="chip-muted bg-white/85 text-slate-700">{formatRole(role)}</span>
  );
}

export function Button({
  className,
  variant = "primary",
  busy = false,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
  busy?: boolean;
}) {
  const variantClass =
    variant === "primary"
      ? "button-primary"
      : variant === "secondary"
        ? "button-secondary"
        : "button-ghost";

  return (
    <button
      className={cn(variantClass, className)}
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
    <label className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-slate-700">{label}</span>
        {hint ? <span className="text-xs text-slate-500">{hint}</span> : null}
      </div>
      {children}
      {error ? <p className="text-sm text-rose-600">{error}</p> : null}
    </label>
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn("input-surface", props.className)} {...props} />;
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn("input-surface min-h-28", props.className)} {...props} />;
}

export function SelectInput(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn("input-surface", props.className)} {...props} />;
}

export function SearchField({
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
      <Search className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
      <TextInput
        className="pl-10"
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

export function FilterTabs({
  value,
  onChange,
  items,
}: {
  value: string;
  onChange: (value: string) => void;
  items: string[];
}) {
  return (
    <div className="flex gap-2 overflow-x-auto pb-1">
      {items.map((item) => {
        const active = item === value;
        return (
          <button
            key={item}
            type="button"
            className={cn(
              "shrink-0 rounded-full px-4 py-2 text-sm font-semibold transition",
              active
                ? "bg-slate-900 text-white shadow-sm"
                : "bg-white/70 text-slate-600 hover:bg-white",
            )}
            onClick={() => onChange(item)}
          >
            {item}
          </button>
        );
      })}
    </div>
  );
}

export function StatPill({
  label,
  value,
  accent = "default",
}: {
  label: string;
  value: string | number;
  accent?: "default" | "accent" | "teal";
}) {
  const accentClass =
    accent === "accent"
      ? "bg-[var(--accent-soft)] text-[var(--accent-strong)]"
      : accent === "teal"
        ? "bg-emerald-100 text-emerald-700"
        : "bg-white/80 text-slate-700";

  return (
    <div className={cn("rounded-[24px] px-4 py-3", accentClass)}>
      <div className="text-xs uppercase tracking-[0.2em] text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
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
    <Panel className="p-8 text-center">
      <div className="space-y-2">
        <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
        <p className="mx-auto max-w-xl text-sm text-slate-600">{description}</p>
      </div>
      {action ? <div className="mt-5 flex justify-center">{action}</div> : null}
    </Panel>
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
    <Panel className="border-rose-200 bg-rose-50/80 p-8 text-center">
      <div className="space-y-2">
        <h3 className="text-lg font-semibold text-rose-700">{title}</h3>
        <p className="mx-auto max-w-xl text-sm text-rose-600">{description}</p>
      </div>
      {action ? <div className="mt-5 flex justify-center">{action}</div> : null}
    </Panel>
  );
}

export function CardSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <Panel className="animate-pulse p-5">
      <div className="space-y-3">
        <div className="h-5 w-32 rounded-full bg-slate-200" />
        {Array.from({ length: lines }).map((_, index) => (
          <div
            key={index}
            className={cn(
              "h-4 rounded-full bg-slate-200",
              index === lines - 1 ? "w-2/3" : "w-full",
            )}
          />
        ))}
      </div>
    </Panel>
  );
}
