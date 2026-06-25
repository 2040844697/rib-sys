import { useDeferredValue, useEffect, useMemo, useState, type ReactNode } from "react";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "@tanstack/react-router";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  ImagePlus,
  Library,
  PackagePlus,
  Pencil,
  Plus,
  Trash2,
  Upload,
  X,
} from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { useAuthState } from "@/lib/auth-store";
import { cn } from "@/lib/utils";
import type { GoodsSummary, GroupBuyItem, MemberSummary, UploadedImageRef } from "@/types";
import {
  Button,
  EmptyState,
  ErrorState,
  LoadingRows,
  PageHeader,
  SearchBox,
  SelectInput,
  Surface,
  TextArea,
  TextInput,
} from "@/components/ui";

type ClaimMode = "拼盒" | "单领";
type SaleMode = "全款" | "定金尾款";

interface FormState {
  title: string;
  description: string;
  groupBuyType: string;
  claimMode: ClaimMode;
  canCancelClaim: boolean;
  startAt: string;
  closeAt: string;
  saleMode: SaleMode;
  allowTransfer: boolean;
  remindBeforeStart: boolean;
  showParticipantCount: boolean;
  showTotalAmount: boolean;
  showClaimedQuantity: boolean;
}

interface EditableItem {
  localId: string;
  persistedId?: string;
  goodsId?: string | null;
  name: string;
  imageUrl: string;
  fileObjectId?: string | null;
  pendingImageFile?: File;
  localImagePreviewUrl?: string;
  localImageName?: string;
  unitPriceCny: string;
  priceAdjustmentCny: string;
  totalQuantity: string;
  initialRecordsEnabled: boolean;
  initialRecords: InitialRecordDraft[];
  weightGram: string;
  characterNames: string[];
  description: string;
  note: string;
  sourceName?: string;
  sourceImageUrl?: string;
  sourceWeightGram?: string;
}

interface InitialRecordDraft {
  localId: string;
  memberUserId: string;
  displayName: string;
  keyword: string;
  quantity: string;
}

interface LocalImageRef extends UploadedImageRef {
  localId: string;
  file?: File;
  previewUrl?: string;
  uploading?: boolean;
}

const groupBuyTypes = ["群内开谷", "群内切煤", "国外全新", "国外二手", "群友出物", "国内现货", "补款", "补寄", "现货加开"];
const claimModes: ClaimMode[] = ["拼盒", "单领"];
const saleModes: SaleMode[] = ["全款", "定金尾款"];

const initialForm: FormState = {
  title: "",
  description: "",
  groupBuyType: "群内开谷",
  claimMode: "单领",
  canCancelClaim: false,
  startAt: "",
  closeAt: "",
  saleMode: "全款",
  allowTransfer: false,
  remindBeforeStart: true,
  showParticipantCount: true,
  showTotalAmount: true,
  showClaimedQuantity: true,
};

function createLocalId(prefix = "local") {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}_${crypto.randomUUID()}`;
  }
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function emptyEditableItem(): EditableItem {
  return {
    localId: createLocalId("item"),
    name: "",
    imageUrl: "",
    unitPriceCny: "",
    priceAdjustmentCny: "0",
    totalQuantity: "1",
    initialRecordsEnabled: false,
    initialRecords: [],
    weightGram: "0",
    characterNames: [],
    description: "",
    note: "",
  };
}

function initialRecordForMember(member?: MemberSummary | null): InitialRecordDraft {
  return {
    localId: createLocalId("record"),
    memberUserId: member?.id || "",
    displayName: member?.displayName || "",
    keyword: member?.displayName || member?.groupNickname || "",
    quantity: "1",
  };
}

function cleanMoney(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return number.toFixed(2).replace(/\.00$/, "").replace(/(\.\d)0$/, "$1");
}

function parseMoney(value: string) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? number : 0;
}

function backendMoney(value: string | number) {
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) {
    throw new Error("金额需要填写为不小于 0 的数字");
  }
  return number.toFixed(2);
}

function parsePositiveInt(value: string, label: string) {
  const number = Number(value);
  if (!Number.isInteger(number) || number <= 0) {
    throw new Error(`${label}需要填写为大于 0 的整数`);
  }
  return number;
}

function parseNonNegativeInt(value: string, label: string) {
  const number = Number(value || 0);
  if (!Number.isInteger(number) || number < 0) {
    throw new Error(`${label}需要填写为不小于 0 的整数`);
  }
  return number;
}

function toDateTimeLocal(value?: string | null) {
  if (!value) return "";
  return value.slice(0, 16);
}

function getItemImage(item: EditableItem) {
  return item.localImagePreviewUrl || item.imageUrl;
}

function getItemFinalPrice(item: EditableItem, equalPriceEnabled: boolean, equalPrice: string) {
  if (!equalPriceEnabled) return parseMoney(item.unitPriceCny);
  return parseMoney(equalPrice) + parseMoney(item.priceAdjustmentCny);
}

function isSnapshotEdited(item: EditableItem) {
  if (!item.goodsId) return false;
  return (
    (item.sourceName !== undefined && item.name !== item.sourceName) ||
    (item.sourceImageUrl !== undefined && item.imageUrl !== item.sourceImageUrl) ||
    (item.sourceWeightGram !== undefined && item.weightGram !== item.sourceWeightGram)
  );
}

function itemFromGoods(goods: GoodsSummary): EditableItem {
  const weight = goods.weightGram === null || goods.weightGram === undefined ? "0" : String(goods.weightGram);
  const price = cleanMoney(goods.domesticSpotSuggestedPriceCny);
  return {
    localId: createLocalId("goods"),
    goodsId: goods.id,
    name: goods.name,
    imageUrl: goods.mainImageUrl || "",
    unitPriceCny: price,
    priceAdjustmentCny: "0",
    totalQuantity: "1",
    initialRecordsEnabled: false,
    initialRecords: [],
    weightGram: weight,
    characterNames: goods.characterNames || [],
    description: goods.description || "",
    note: "",
    sourceName: goods.name,
    sourceImageUrl: goods.mainImageUrl || "",
    sourceWeightGram: weight,
  };
}

function itemFromDetail(item: GroupBuyItem): EditableItem {
  const weight = item.weightGram ?? item.estimatedWeightGram ?? 0;
  return {
    localId: item.id,
    persistedId: item.id,
    goodsId: item.goodsId,
    name: item.name,
    imageUrl: item.imageUrl || "",
    unitPriceCny: cleanMoney(item.unitPriceCny),
    priceAdjustmentCny: "0",
    totalQuantity: String(item.totalQuantity ?? 1),
    initialRecordsEnabled: false,
    initialRecords: [],
    weightGram: String(weight ?? 0),
    characterNames: item.characterNames || (item.characterName ? [item.characterName] : []),
    description: item.description || "",
    note: item.note || "",
    sourceName: item.name,
    sourceImageUrl: item.imageUrl || "",
    sourceWeightGram: String(weight ?? 0),
  };
}

function createItemPayload(item: EditableItem, groupBuyId: string, equalPriceEnabled: boolean, equalPrice: string, includeGoodsId: boolean) {
  const totalQuantity = parsePositiveInt(item.totalQuantity, "库存");
  const initialRecords = item.initialRecordsEnabled
    ? item.initialRecords.map((record) => ({
        memberUserId: record.memberUserId,
        quantity: parsePositiveInt(record.quantity, `${item.name || "谷子"}初始化拼单记录数量`),
      }))
    : [];
  const initialRecordTotal = initialRecords.reduce((sum, record) => sum + record.quantity, 0);
  if (initialRecordTotal > totalQuantity) throw new Error("初始化拼单记录数量不能大于库存");

  const weightGram = parseNonNegativeInt(item.weightGram || "0", "重量");
  const unitPriceCny = backendMoney(getItemFinalPrice(item, equalPriceEnabled, equalPrice));
  const imageUrl = item.imageUrl.trim();

  return {
    groupBuyId,
    ...(includeGoodsId && item.goodsId ? { goodsId: item.goodsId } : {}),
    name: item.name.trim(),
    imageUrl: imageUrl || undefined,
    unitPriceCny,
    totalQuantity,
    initialRecords: initialRecords.length ? initialRecords : undefined,
    weightGram,
    characterNames: item.characterNames,
    description: item.description.trim() || undefined,
    note: item.note.trim() || undefined,
    reason: "页面编辑谷子",
  };
}

function validateItem(item: EditableItem, equalPriceEnabled: boolean, equalPrice: string) {
  if (!item.name.trim()) throw new Error("请补全谷子名称");
  const price = getItemFinalPrice(item, equalPriceEnabled, equalPrice);
  if (!Number.isFinite(price) || price < 0) throw new Error(`${item.name || "谷子"} 的价格不正确`);
  const totalQuantity = parsePositiveInt(item.totalQuantity, `${item.name || "谷子"}库存`);
  if (item.initialRecordsEnabled) {
    if (item.initialRecords.length === 0) throw new Error(`${item.name || "谷子"}需要至少添加一条初始化拼单记录`);
    const seenMemberIds = new Set<string>();
    const initialRecordTotal = item.initialRecords.reduce((sum, record) => {
      if (!record.memberUserId) throw new Error(`${item.name || "谷子"}的归属人需要从匹配结果中选择`);
      if (seenMemberIds.has(record.memberUserId)) throw new Error(`${item.name || "谷子"}的归属人不能重复`);
      seenMemberIds.add(record.memberUserId);
      return sum + parsePositiveInt(record.quantity, `${item.name || "谷子"}初始化拼单记录数量`);
    }, 0);
    if (initialRecordTotal > totalQuantity) throw new Error(`${item.name || "谷子"}初始化拼单记录数量不能大于库存`);
  }
  parseNonNegativeInt(item.weightGram || "0", `${item.name || "谷子"}重量`);
}

function getInitialRecordTotal(item: EditableItem) {
  if (!item.initialRecordsEnabled) return 0;
  return item.initialRecords.reduce((sum, record) => {
    const quantity = Number(record.quantity || 0);
    if (!Number.isFinite(quantity) || quantity < 0) return sum;
    return sum + quantity;
  }, 0);
}

function formatSaveError(error: Error) {
  if (error instanceof ApiError) {
    return `${error.message}（HTTP ${error.status}${error.code ? ` / ${error.code}` : ""}）`;
  }
  return error.message;
}

function SectionLabel({ children }: { children: ReactNode }) {
  return <h2 className="px-1 text-sm font-semibold text-cyan-600">{children}</h2>;
}

function SettingPanel({ children }: { children: ReactNode }) {
  return <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">{children}</div>;
}

function SettingRow({
  label,
  children,
  onClick,
  className,
}: {
  label: string;
  children: ReactNode;
  onClick?: () => void;
  className?: string;
}) {
  return (
    <button
      className={cn(
        "flex min-h-14 w-full items-center justify-between gap-4 border-t border-slate-100 px-4 py-3 text-left first:border-t-0",
        onClick ? "hover:bg-slate-50" : "cursor-default",
        className,
      )}
      onClick={onClick}
      type="button"
    >
      <span className="text-sm font-semibold text-slate-950">{label}</span>
      {children}
    </button>
  );
}

function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: T[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="inline-flex rounded-md bg-slate-100 p-1">
      {options.map((option) => (
        <button
          key={option}
          className={cn(
            "min-h-8 rounded px-3 text-sm font-semibold transition",
            option === value ? "bg-white text-cyan-700 shadow-sm" : "text-slate-500 hover:text-slate-900",
          )}
          onClick={(event) => {
            event.stopPropagation();
            onChange(option);
          }}
          type="button"
        >
          {option}
        </button>
      ))}
    </div>
  );
}

function Toggle({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <button
      aria-pressed={checked}
      className={cn(
        "relative h-7 w-12 rounded-full transition",
        checked ? "bg-cyan-600" : "bg-slate-300",
      )}
      onClick={(event) => {
        event.stopPropagation();
        onChange(!checked);
      }}
      type="button"
    >
      <span
        className={cn(
          "absolute top-1 size-5 rounded-full bg-white shadow transition",
          checked ? "left-6" : "left-1",
        )}
      />
    </button>
  );
}

function Modal({
  open,
  title,
  children,
  onClose,
  wide = false,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/35 p-3 sm:items-center">
      <div
        className={cn(
          "max-h-[88vh] w-full overflow-hidden rounded-lg bg-white shadow-2xl",
          wide ? "max-w-5xl" : "max-w-lg",
        )}
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <h3 className="text-base font-semibold text-slate-950">{title}</h3>
          <button className="btn btn-quiet size-9 p-0" onClick={onClose} type="button">
            <X className="size-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function ImageTile({
  title,
  subtitle,
  imageUrl,
  onFile,
}: {
  title: string;
  subtitle?: string;
  imageUrl?: string;
  onFile: (file: File) => void;
}) {
  return (
    <label className="flex size-28 cursor-pointer flex-col items-center justify-center overflow-hidden rounded-lg bg-slate-100 text-center text-slate-500 transition hover:bg-slate-200">
      <input
        accept="image/*"
        className="sr-only"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onFile(file);
        }}
        type="file"
      />
      {imageUrl ? (
        <img alt="" className="size-full object-cover" src={imageUrl} />
      ) : (
        <>
          <Plus className="size-9" />
          <span className="mt-1 text-xs font-semibold">{title}</span>
          {subtitle ? <span className="text-[11px]">{subtitle}</span> : null}
        </>
      )}
    </label>
  );
}

function MultiImageUploader({
  images,
  onAdd,
  onRemove,
}: {
  images: LocalImageRef[];
  onAdd: (files: File[]) => void;
  onRemove: (localId: string) => void;
}) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-3">
        {images.map((image, index) => (
          <div className="group relative size-28 overflow-hidden rounded-lg bg-slate-100" key={image.localId}>
            <img alt="" className="size-full object-cover" src={image.previewUrl || image.url} />
            {index === 0 ? (
              <span className="absolute left-2 top-2 rounded bg-cyan-600 px-1.5 py-0.5 text-[11px] font-semibold text-white">
                主图
              </span>
            ) : null}
            {image.uploading ? (
              <span className="absolute inset-x-2 bottom-2 rounded bg-white/90 px-2 py-1 text-center text-[11px] font-semibold text-slate-600">
                待上传
              </span>
            ) : null}
            <button
              className="absolute right-1.5 top-1.5 flex size-7 items-center justify-center rounded-full bg-white/90 text-slate-600 opacity-0 shadow transition hover:text-rose-600 group-hover:opacity-100"
              onClick={() => onRemove(image.localId)}
              type="button"
            >
              <X className="size-4" />
            </button>
          </div>
        ))}
        <label className="flex size-28 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50 text-center text-slate-500 transition hover:border-cyan-400 hover:bg-cyan-50 hover:text-cyan-700">
          <input
            accept="image/*"
            className="sr-only"
            multiple
            onChange={(event) => {
              const files = Array.from(event.target.files || []);
              if (files.length) onAdd(files);
              event.target.value = "";
            }}
            type="file"
          />
          <ImagePlus className="size-8" />
          <span className="mt-1 text-xs font-semibold">上传活动图</span>
          <span className="text-[11px]">可多选</span>
        </label>
      </div>
      {images.length ? (
        <p className="text-xs text-slate-500">第一张会作为拼团卡片主图，其他图片会随拼团配置保存。</p>
      ) : null}
    </div>
  );
}

function PriceDisplay({
  item,
  equalPriceEnabled,
  equalPrice,
}: {
  item: EditableItem;
  equalPriceEnabled: boolean;
  equalPrice: string;
}) {
  if (!equalPriceEnabled) {
    return <span className="text-lg font-semibold text-rose-600">¥{cleanMoney(item.unitPriceCny) || "0"}</span>;
  }

  const adjustment = parseMoney(item.priceAdjustmentCny);
  const adjustmentText = adjustment > 0 ? `+${cleanMoney(adjustment)}` : cleanMoney(adjustment);
  return (
    <span className="text-lg font-semibold">
      <span className="text-slate-950">¥{cleanMoney(equalPrice) || "0"}</span>
      <span className={cn("ml-1", adjustment > 0 ? "text-rose-600" : adjustment < 0 ? "text-sky-600" : "text-slate-400")}>
        {adjustmentText}
      </span>
    </span>
  );
}

function ItemCard({
  item,
  equalPriceEnabled,
  equalPrice,
  onEdit,
  onCopy,
  onDelete,
}: {
  item: EditableItem;
  equalPriceEnabled: boolean;
  equalPrice: string;
  onEdit: () => void;
  onCopy: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="grid gap-3 rounded-lg border border-slate-200 bg-white p-3 sm:grid-cols-[92px_1fr]">
      <div className="flex aspect-square items-center justify-center overflow-hidden rounded-lg bg-slate-100 text-slate-400">
        {getItemImage(item) ? (
          <img alt="" className="size-full object-cover" src={getItemImage(item)} />
        ) : (
          <ImagePlus className="size-8" />
        )}
      </div>
      <div className="min-w-0">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h3 className="truncate text-base font-semibold text-slate-950">{item.name || "未命名谷子"}</h3>
            <p className="mt-1 text-sm text-slate-500">
              库存:{item.totalQuantity || 0}
              <span className="mx-2 text-slate-300">/</span>
              已建单:{getInitialRecordTotal(item)}
              <span className="mx-2 text-slate-300">/</span>
              重量:{item.weightGram || 0}g
            </p>
            {item.characterNames.length ? (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {item.characterNames.slice(0, 3).map((name) => (
                  <span className="badge-neutral" key={name}>{name}</span>
                ))}
              </div>
            ) : null}
          </div>
          <PriceDisplay equalPrice={equalPrice} equalPriceEnabled={equalPriceEnabled} item={item} />
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button className="min-h-8 px-3 py-1.5" onClick={onEdit} type="button" variant="secondary">
            <Pencil className="size-4" />
            编辑
          </Button>
          <Button className="min-h-8 px-3 py-1.5" onClick={onCopy} type="button" variant="secondary">
            <Copy className="size-4" />
            复制
          </Button>
          <Button className="min-h-8 px-3 py-1.5" onClick={onDelete} type="button" variant="secondary">
            <Trash2 className="size-4" />
            删除
          </Button>
        </div>
      </div>
    </div>
  );
}

function ItemEditorModal({
  item,
  groupId,
  currentUser,
  equalPriceEnabled,
  equalPrice,
  onSave,
  onClose,
}: {
  item: EditableItem | null;
  groupId: string;
  currentUser: MemberSummary | null;
  equalPriceEnabled: boolean;
  equalPrice: string;
  onSave: (item: EditableItem) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<EditableItem | null>(item);
  const [activeRecordId, setActiveRecordId] = useState<string | null>(null);

  useEffect(() => {
    setDraft(item);
    setActiveRecordId(null);
  }, [item]);

  const activeRecord = draft?.initialRecords.find((record) => record.localId === activeRecordId);
  const deferredMemberKeyword = useDeferredValue(activeRecord?.keyword || "");
  const membersQuery = useQuery({
    queryKey: ["group-members", groupId, deferredMemberKeyword],
    queryFn: () => api.searchGroupMembers(groupId, { keyword: deferredMemberKeyword, pageSize: 8 }),
    enabled: Boolean(groupId && draft?.initialRecordsEnabled && activeRecordId),
    placeholderData: keepPreviousData,
  });

  if (!draft) return null;

  const finalPrice = getItemFinalPrice(draft, equalPriceEnabled, equalPrice);
  const initialRecordTotal = getInitialRecordTotal(draft);
  const stockQuantity = Number(draft.totalQuantity || 0);
  const initialRecordTooLarge = Number.isFinite(stockQuantity) && initialRecordTotal > stockQuantity;

  function setInitialRecordsEnabled(enabled: boolean) {
    setDraft((current) => {
      if (!current) return current;
      if (!enabled) {
        setActiveRecordId(null);
        return { ...current, initialRecordsEnabled: false, initialRecords: [] };
      }
      const nextRecords = current.initialRecords.length
        ? current.initialRecords
        : [initialRecordForMember(currentUser)];
      setActiveRecordId(nextRecords[0]?.localId || null);
      return { ...current, initialRecordsEnabled: true, initialRecords: nextRecords };
    });
  }

  function updateInitialRecord(localId: string, patch: Partial<InitialRecordDraft>) {
    setDraft((current) => current
      ? {
          ...current,
          initialRecords: current.initialRecords.map((record) => (
            record.localId === localId ? { ...record, ...patch } : record
          )),
        }
      : current);
  }

  function addInitialRecord() {
    setDraft((current) => {
      if (!current) return current;
      const nextRecord = initialRecordForMember(currentUser);
      setActiveRecordId(nextRecord.localId);
      return { ...current, initialRecords: [...current.initialRecords, nextRecord] };
    });
  }

  function removeInitialRecord(localId: string) {
    setDraft((current) => {
      if (!current) return current;
      const nextRecords = current.initialRecords.filter((record) => record.localId !== localId);
      if (activeRecordId === localId) setActiveRecordId(nextRecords[0]?.localId || null);
      return {
        ...current,
        initialRecords: nextRecords,
        initialRecordsEnabled: nextRecords.length > 0,
      };
    });
  }

  function chooseMember(localId: string, member: MemberSummary) {
    updateInitialRecord(localId, {
      memberUserId: member.id,
      displayName: member.displayName,
      keyword: member.displayName,
    });
    setActiveRecordId(null);
  }

  return (
    <Modal onClose={onClose} open={Boolean(item)} title="编辑谷子">
      <div className="max-h-[calc(88vh-73px)] overflow-y-auto p-5">
        <div className="grid gap-4 sm:grid-cols-[120px_1fr]">
          <ImageTile
            imageUrl={getItemImage(draft)}
            onFile={(file) => {
              setDraft({
                ...draft,
                pendingImageFile: file,
                localImagePreviewUrl: URL.createObjectURL(file),
                localImageName: file.name,
              });
            }}
            subtitle={draft.localImageName}
            title="上传图片"
          />
          <div className="space-y-3">
            <TextInput
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              placeholder="谷子名称"
              value={draft.name}
            />
            <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-500">
              {draft.localImageName || "上传后会自动保存为谷子图片"}
            </div>
          </div>
        </div>

        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          {equalPriceEnabled ? (
            <>
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-slate-700">均价</span>
                <TextInput disabled value={cleanMoney(equalPrice) || "0"} />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-slate-700">调价</span>
                <TextInput
                  inputMode="decimal"
                  onChange={(event) => setDraft({ ...draft, priceAdjustmentCny: event.target.value })}
                  placeholder="例如 2 或 -1"
                  value={draft.priceAdjustmentCny}
                />
              </label>
              <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600 sm:col-span-2">
                当前显示价 <span className="font-semibold text-slate-950">¥{cleanMoney(finalPrice)}</span>
              </div>
            </>
          ) : (
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-slate-700">价格</span>
              <TextInput
                inputMode="decimal"
                onChange={(event) => setDraft({ ...draft, unitPriceCny: event.target.value })}
                placeholder="0.00"
                value={draft.unitPriceCny}
              />
            </label>
          )}
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-slate-700">库存</span>
            <TextInput
              inputMode="numeric"
              onChange={(event) => setDraft({ ...draft, totalQuantity: event.target.value })}
              value={draft.totalQuantity}
            />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-slate-700">重量(g)</span>
            <TextInput
              inputMode="numeric"
              onChange={(event) => setDraft({ ...draft, weightGram: event.target.value })}
              placeholder="0"
              value={draft.weightGram}
            />
          </label>
        </div>

        <div className="mt-5 rounded-lg border border-slate-200 bg-slate-50 p-3">
          <label className="flex items-center justify-between gap-3">
            <span>
              <span className="block text-sm font-semibold text-slate-950">是否预留（自留）</span>
              <span className="mt-1 block text-xs leading-5 text-slate-500">
                保存后会创建对应拼单记录，并同步扣减可拼库存。
              </span>
            </span>
            <input
              checked={draft.initialRecordsEnabled}
              className="size-4 accent-cyan-600"
              onChange={(event) => setInitialRecordsEnabled(event.target.checked)}
              type="checkbox"
            />
          </label>

          {draft.initialRecordsEnabled ? (
            <div className="mt-3 space-y-3">
              {draft.initialRecords.map((record) => (
                <div className="rounded-lg border border-slate-200 bg-white p-3" key={record.localId}>
                  <div className="grid gap-3 sm:grid-cols-[1fr_110px_auto]">
                    <div className="relative">
                      <span className="mb-1.5 block text-sm font-medium text-slate-700">归属人</span>
                      <TextInput
                        onBlur={() => {
                          window.setTimeout(() => {
                            if (activeRecordId === record.localId) setActiveRecordId(null);
                          }, 120);
                        }}
                        onChange={(event) => {
                          updateInitialRecord(record.localId, {
                            keyword: event.target.value,
                            memberUserId: "",
                            displayName: "",
                          });
                          setActiveRecordId(record.localId);
                        }}
                        onFocus={() => setActiveRecordId(record.localId)}
                        placeholder="输入昵称、QQ 或账号"
                        value={record.keyword}
                      />
                      {activeRecordId === record.localId ? (
                        <div className="absolute left-0 right-0 top-full z-20 mt-1 max-h-48 overflow-y-auto rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
                          {membersQuery.isLoading ? (
                            <div className="px-3 py-2 text-sm text-slate-500">搜索中...</div>
                          ) : null}
                          {membersQuery.isError ? (
                            <div className="px-3 py-2 text-sm text-rose-600">成员搜索失败</div>
                          ) : null}
                          {membersQuery.data?.items.length === 0 ? (
                            <div className="px-3 py-2 text-sm text-slate-500">没有匹配成员</div>
                          ) : null}
                          {membersQuery.data?.items.map((member) => (
                            <button
                              className="flex w-full flex-col rounded-md px-3 py-2 text-left hover:bg-cyan-50"
                              key={member.id}
                              onMouseDown={(event) => event.preventDefault()}
                              onClick={() => chooseMember(record.localId, member)}
                              type="button"
                            >
                              <span className="text-sm font-semibold text-slate-950">{member.displayName}</span>
                              <span className="text-xs text-slate-500">
                                {member.groupNickname || "未填群昵称"}
                                {member.qqNumber ? ` · ${member.qqNumber}` : ""}
                              </span>
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>

                    <label className="block">
                      <span className="mb-1.5 block text-sm font-medium text-slate-700">数量</span>
                      <TextInput
                        inputMode="numeric"
                        onChange={(event) => updateInitialRecord(record.localId, { quantity: event.target.value })}
                        value={record.quantity}
                      />
                    </label>

                    <div className="flex items-end">
                      <Button
                        className="min-h-10 px-3"
                        disabled={draft.initialRecords.length <= 1}
                        onClick={() => removeInitialRecord(record.localId)}
                        type="button"
                        variant="secondary"
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  </div>
                  {record.memberUserId ? (
                    <div className="mt-2 text-xs text-cyan-700">已选择：{record.displayName || record.keyword}</div>
                  ) : (
                    <div className="mt-2 text-xs text-amber-700">需要从匹配结果中选择归属人</div>
                  )}
                </div>
              ))}

              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <Button onClick={addInitialRecord} type="button" variant="secondary">
                  <Plus className="size-4" />
                  添加归属人
                </Button>
                <div className={cn("text-sm", initialRecordTooLarge ? "text-rose-600" : "text-slate-500")}>
                  已建单数量 {initialRecordTotal} / 库存 {draft.totalQuantity || 0}
                </div>
              </div>
            </div>
          ) : null}
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <Button onClick={onClose} type="button" variant="secondary">取消</Button>
          <Button
            onClick={() => {
              if (initialRecordTooLarge) return;
              onSave({
                ...draft,
                unitPriceCny: equalPriceEnabled ? cleanMoney(finalPrice) : draft.unitPriceCny,
                weightGram: draft.weightGram || "0",
              });
            }}
            type="button"
          >
            保存
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function GoodsImportModal({
  open,
  onClose,
  onAdd,
}: {
  open: boolean;
  onClose: () => void;
  onAdd: (items: GoodsSummary[]) => void;
}) {
  const [keyword, setKeyword] = useState("");
  const [characterName, setCharacterName] = useState("");
  const [seriesName, setSeriesName] = useState("");
  const [status, setStatus] = useState("enabled");
  const [selected, setSelected] = useState<Map<string, GoodsSummary>>(new Map());
  const deferredKeyword = useDeferredValue(keyword);

  const query = useQuery({
    queryKey: ["goods-import", deferredKeyword, characterName, seriesName, status],
    queryFn: () => api.searchGoods({
      keyword: deferredKeyword,
      characterName,
      seriesName,
      status,
      pageSize: 50,
    }),
    enabled: open,
    placeholderData: keepPreviousData,
  });

  useEffect(() => {
    if (!open) setSelected(new Map());
  }, [open]);

  const selectedItems = Array.from(selected.values());

  return (
    <Modal onClose={onClose} open={open} title="从商品库导入" wide>
      <div className="grid max-h-[calc(88vh-73px)] grid-rows-[auto_1fr_auto] overflow-hidden">
        <div className="border-b border-slate-200 p-4">
          <div className="grid gap-3 lg:grid-cols-[1fr_180px_180px_140px]">
            <SearchBox onChange={setKeyword} placeholder="搜索商品名、别名、系列" value={keyword} />
            <TextInput onChange={(event) => setCharacterName(event.target.value)} placeholder="角色筛选" value={characterName} />
            <TextInput onChange={(event) => setSeriesName(event.target.value)} placeholder="系列筛选" value={seriesName} />
            <SelectInput onChange={(event) => setStatus(event.target.value)} value={status}>
              <option value="">全部状态</option>
              <option value="enabled">启用</option>
              <option value="draft">草稿</option>
              <option value="disabled">停用</option>
            </SelectInput>
          </div>
        </div>

        <div className="overflow-y-auto bg-slate-50 p-4">
          {query.isLoading ? <LoadingRows rows={4} /> : null}
          {query.isError ? <ErrorState title="商品库加载失败" description={query.error.message} /> : null}
          {query.data?.items.length === 0 ? <EmptyState title="暂无商品" description="当前筛选下没有可导入商品。" /> : null}
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {query.data?.items.map((goods) => {
              const checked = selected.has(goods.id);
              return (
                <button
                  className={cn(
                    "grid grid-cols-[76px_1fr] gap-3 rounded-lg border bg-white p-3 text-left transition",
                    checked ? "border-cyan-500 ring-2 ring-cyan-100" : "border-slate-200 hover:border-cyan-300",
                  )}
                  key={goods.id}
                  onClick={() => {
                    setSelected((current) => {
                      const next = new Map(current);
                      if (next.has(goods.id)) next.delete(goods.id);
                      else next.set(goods.id, goods);
                      return next;
                    });
                  }}
                  type="button"
                >
                  <div className="relative flex aspect-square items-center justify-center overflow-hidden rounded-lg bg-slate-100 text-slate-400">
                    {goods.mainImageUrl ? <img alt="" className="size-full object-cover" src={goods.mainImageUrl} /> : <ImagePlus className="size-7" />}
                    <span className={cn(
                      "absolute right-1.5 top-1.5 flex size-5 items-center justify-center rounded-full border bg-white",
                      checked ? "border-cyan-500 text-cyan-600" : "border-slate-300 text-transparent",
                    )}>
                      <Check className="size-3.5" />
                    </span>
                  </div>
                  <div className="min-w-0">
                    <h4 className="truncate text-sm font-semibold text-slate-950">{goods.name}</h4>
                    <p className="mt-1 truncate text-xs text-slate-500">{goods.seriesName || "未分系列"}</p>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {goods.characterNames?.slice(0, 2).map((name) => (
                        <span className="badge-neutral" key={name}>{name}</span>
                      ))}
                    </div>
                    <p className="mt-2 text-xs text-slate-500">
                      {goods.weightGram ?? 0}g
                      {goods.domesticSpotSuggestedPriceCny ? ` · ¥${cleanMoney(goods.domesticSpotSuggestedPriceCny)}` : ""}
                    </p>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex flex-col gap-3 border-t border-slate-200 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-sm text-slate-600">已选择 <span className="font-semibold text-cyan-700">{selectedItems.length}</span> 个商品</div>
          <div className="flex gap-2">
            <Button onClick={onClose} type="button" variant="secondary">退出</Button>
            <Button disabled={selectedItems.length === 0} onClick={() => onAdd(selectedItems)} type="button">
              添加
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

export function GroupBuyFormPage() {
  const params = useParams({ strict: false }) as { groupId?: string; groupBuyId?: string };
  const routeGroupId = params.groupId;
  const groupBuyId = params.groupBuyId;
  const navigate = useNavigate();
  const auth = useAuthState();
  const [form, setForm] = useState<FormState>(initialForm);
  const [items, setItems] = useState<EditableItem[]>([]);
  const [itemsExpanded, setItemsExpanded] = useState(false);
  const [equalPriceEnabled, setEqualPriceEnabled] = useState(false);
  const [equalPrice, setEqualPrice] = useState("");
  const [editingItem, setEditingItem] = useState<EditableItem | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [coverImages, setCoverImages] = useState<LocalImageRef[]>([]);
  const [deleteWarning, setDeleteWarning] = useState("");

  const detailQuery = useQuery({
    queryKey: ["group-buy-detail", groupBuyId],
    queryFn: () => api.getGroupBuyDetail(groupBuyId || ""),
    enabled: Boolean(groupBuyId),
  });
  const groupsQuery = useQuery({
    queryKey: ["groups"],
    queryFn: () => api.getGroups(),
    enabled: !routeGroupId && !groupBuyId,
  });

  const activeGroupId = routeGroupId || detailQuery.data?.groupBuy.groupId || groupsQuery.data?.items[0]?.id || "";
  const groupHomeQuery = useQuery({
    queryKey: ["group-home", activeGroupId],
    queryFn: () => api.getGroupHome(activeGroupId),
    enabled: Boolean(activeGroupId),
  });

  useEffect(() => {
    if (!detailQuery.data) return;
    const detail = detailQuery.data;
    setForm((current) => ({
      ...current,
      title: detail.groupBuy.title,
      description: detail.groupBuy.description || "",
      groupBuyType: detail.groupBuy.type,
      claimMode: detail.groupBuy.claimMode === "拼盒" ? "拼盒" : "单领",
      canCancelClaim: Boolean(detail.groupBuy.canCancelClaim),
      startAt: toDateTimeLocal(detail.groupBuy.startAt),
      closeAt: toDateTimeLocal(detail.groupBuy.closeAt),
      saleMode: detail.groupBuy.saleMode === "定金尾款" ? "定金尾款" : "全款",
      allowTransfer: Boolean(detail.groupBuy.allowTransfer),
      remindBeforeStart: detail.groupBuy.advancedSettings?.remindBeforeStart ?? current.remindBeforeStart,
      showParticipantCount: detail.groupBuy.advancedSettings?.showParticipantCount ?? current.showParticipantCount,
      showTotalAmount: detail.groupBuy.advancedSettings?.showTotalAmount ?? current.showTotalAmount,
      showClaimedQuantity: detail.groupBuy.advancedSettings?.showClaimedQuantity ?? current.showClaimedQuantity,
    }));
    const restoredImages = detail.groupBuy.advancedSettings?.coverImages?.length
      ? detail.groupBuy.advancedSettings.coverImages
      : detail.groupBuy.coverImageUrl
        ? [{ fileObjectId: detail.groupBuy.coverFileObjectId, url: detail.groupBuy.coverImageUrl, name: "活动主图" }]
        : [];
    setCoverImages(restoredImages.map((image, index) => ({
      localId: image.fileObjectId || `cover_${index}`,
      fileObjectId: image.fileObjectId,
      url: image.url,
      name: image.name,
    })));
    setItems(detail.items.map(itemFromDetail));
    setItemsExpanded(detail.items.length > 0);
  }, [detailQuery.data]);

  const firstItem = items[0];
  const hiddenItemCount = Math.max(items.length - 1, 0);
  const groupName = groupHomeQuery.data?.group.name || groupsQuery.data?.items.find((group) => group.id === activeGroupId)?.name;
  const currentMember: MemberSummary | null = auth.user
    ? {
        id: auth.user.id,
        groupId: auth.user.groupId,
        displayName: auth.user.displayName,
        groupNickname: auth.user.groupNickname,
        qqNumber: auth.user.qqNumber,
      }
    : null;

  async function uploadLocalImage(image: LocalImageRef) {
    if (!image.file) return image;
    const uploaded = await api.uploadFile(image.file, "misc");
    return {
      ...image,
      file: undefined,
      previewUrl: undefined,
      uploading: false,
      fileObjectId: uploaded.fileObjectId,
      url: uploaded.url,
      name: image.name || image.file.name,
    };
  }

  async function uploadItemImage(item: EditableItem) {
    if (!item.pendingImageFile) return item;
    const uploaded = await api.uploadFile(item.pendingImageFile, "misc");
    return {
      ...item,
      pendingImageFile: undefined,
      localImagePreviewUrl: undefined,
      fileObjectId: uploaded.fileObjectId,
      imageUrl: uploaded.url,
    };
  }

  const save = useMutation({
    mutationFn: async () => {
      const groupId = activeGroupId;
      if (!groupId) throw new Error("请从谷团详情页进入新建拼团");
      if (form.title.trim().length < 2) throw new Error("请填写至少 2 个字的拼团标题");
      if (equalPriceEnabled && !equalPrice.trim()) throw new Error("开启均价后需要填写均价");
      items.forEach((item) => validateItem(item, equalPriceEnabled, equalPrice));

      const uploadedCoverImages = await Promise.all(coverImages.map((image) => uploadLocalImage(image)));
      setCoverImages(uploadedCoverImages);
      const uploadedItems = await Promise.all(items.map((item) => uploadItemImage(item)));
      setItems(uploadedItems);

      const primaryImage = uploadedCoverImages[0];
      const coverImagePayload = uploadedCoverImages.map(({ fileObjectId, url, name }) => ({
        fileObjectId,
        url,
        name,
      }));

      const basePayload = {
        groupId,
        type: form.groupBuyType,
        title: form.title.trim(),
        description: form.description.trim(),
        closeAt: form.closeAt,
        startAt: form.startAt,
        coverFileObjectId: primaryImage?.fileObjectId || undefined,
        coverImageUrl: primaryImage?.url || undefined,
        claimMode: form.claimMode,
        canCancelClaim: form.canCancelClaim,
        saleMode: form.saleMode,
        allowTransfer: form.allowTransfer,
        advancedSettings: {
          remindBeforeStart: form.remindBeforeStart,
          showParticipantCount: form.showParticipantCount,
          showTotalAmount: form.showTotalAmount,
          showClaimedQuantity: form.showClaimedQuantity,
          coverImages: coverImagePayload,
        },
        reason: "页面编辑拼团",
      };

      const original = detailQuery.data?.groupBuy;
      const originalAdvanced = original?.advancedSettings || {};
      const originalImages = originalAdvanced.coverImages?.length
        ? originalAdvanced.coverImages
        : original?.coverImageUrl
          ? [{ fileObjectId: original.coverFileObjectId, url: original.coverImageUrl, name: "活动主图" }]
          : [];
      const groupChanged = !original || (
        form.title.trim() !== original.title ||
        form.description.trim() !== (original.description || "") ||
        form.groupBuyType !== original.type ||
        form.startAt !== toDateTimeLocal(original.startAt) ||
        form.closeAt !== toDateTimeLocal(original.closeAt) ||
        primaryImage?.fileObjectId !== (original.coverFileObjectId || undefined) ||
        primaryImage?.url !== (original.coverImageUrl || undefined) ||
        form.claimMode !== (original.claimMode || "单领") ||
        form.canCancelClaim !== Boolean(original.canCancelClaim) ||
        form.saleMode !== (original.saleMode || "全款") ||
        form.allowTransfer !== Boolean(original.allowTransfer) ||
        form.remindBeforeStart !== (originalAdvanced.remindBeforeStart ?? initialForm.remindBeforeStart) ||
        form.showParticipantCount !== (originalAdvanced.showParticipantCount ?? initialForm.showParticipantCount) ||
        form.showTotalAmount !== (originalAdvanced.showTotalAmount ?? initialForm.showTotalAmount) ||
        form.showClaimedQuantity !== (originalAdvanced.showClaimedQuantity ?? initialForm.showClaimedQuantity) ||
        JSON.stringify(coverImagePayload) !== JSON.stringify(originalImages)
      );

      let nextGroupBuyId = groupBuyId;
      if (groupBuyId) {
        if (groupChanged) await api.updateGroupBuy(groupBuyId, basePayload);
      } else {
        const created = await api.createGroupBuy(basePayload);
        nextGroupBuyId = created.groupBuyId;
      }

      if (!nextGroupBuyId) throw new Error("后端没有返回拼团 ID");

      for (const item of uploadedItems) {
        const includeGoodsId = Boolean(item.goodsId && !item.persistedId);
        if (item.persistedId) {
          if (item.initialRecordsEnabled && item.initialRecords.length > 0) {
            throw new Error("已保存谷子的初始化拼单记录不能在编辑页重复创建，请到拼单详情里管理记录。");
          }
          await api.updateGroupBuyItem(
            item.persistedId,
            createItemPayload(item, nextGroupBuyId, equalPriceEnabled, equalPrice, false),
          );
          continue;
        }

        const createdItem = await api.createGroupBuyItem(
          createItemPayload(item, nextGroupBuyId, equalPriceEnabled, equalPrice, includeGoodsId),
        );

        if (item.goodsId && isSnapshotEdited(item) && createdItem.groupBuyItemId) {
          await api.updateGroupBuyItem(
            createdItem.groupBuyItemId,
            createItemPayload(item, nextGroupBuyId, equalPriceEnabled, equalPrice, false),
          );
        }
      }

      return nextGroupBuyId;
    },
    onSuccess: (nextGroupBuyId) => {
      void navigate({ to: "/app/group-buys/$groupBuyId", params: { groupBuyId: nextGroupBuyId } });
    },
  });

  function updateForm(patch: Partial<FormState>) {
    setForm((current) => ({ ...current, ...patch }));
  }

  function addCoverFiles(files: File[]) {
    setCoverImages((current) => [
      ...current,
      ...files.map((file) => ({
        localId: createLocalId("cover"),
        file,
        previewUrl: URL.createObjectURL(file),
        url: "",
        name: file.name,
        uploading: true,
      })),
    ]);
  }

  function removeCoverImage(localId: string) {
    setCoverImages((current) => current.filter((image) => image.localId !== localId));
  }

  function toggleEqualPrice() {
    if (equalPriceEnabled) {
      setItems((current) => current.map((item) => ({
        ...item,
        unitPriceCny: cleanMoney(getItemFinalPrice(item, true, equalPrice)),
        priceAdjustmentCny: "0",
      })));
      setEqualPriceEnabled(false);
      return;
    }

    const nextEqualPrice = equalPrice || items[0]?.unitPriceCny || "0";
    setEqualPrice(cleanMoney(nextEqualPrice));
    setItems((current) => current.map((item) => ({
      ...item,
      priceAdjustmentCny: cleanMoney(parseMoney(item.unitPriceCny) - parseMoney(nextEqualPrice)),
    })));
    setEqualPriceEnabled(true);
  }

  function upsertItem(nextItem: EditableItem) {
    setItems((current) => {
      const exists = current.some((item) => item.localId === nextItem.localId);
      if (exists) return current.map((item) => item.localId === nextItem.localId ? nextItem : item);
      return [...current, nextItem];
    });
    setItemsExpanded(true);
    setEditingItem(null);
  }

  function copyItem(item: EditableItem) {
    setItems((current) => [
      ...current,
      {
        ...item,
        localId: createLocalId("copy"),
        persistedId: undefined,
        name: `${item.name} 复制`,
        initialRecordsEnabled: false,
        initialRecords: [],
      },
    ]);
    setItemsExpanded(true);
  }

  function deleteItem(item: EditableItem) {
    if (item.persistedId) {
      setDeleteWarning("已保存谷子的删除接口后端暂未提供，当前只能删除本次新加的谷子。");
      return;
    }
    setItems((current) => current.filter((candidate) => candidate.localId !== item.localId));
  }

  if (detailQuery.isLoading || groupsQuery.isLoading) return <LoadingRows rows={3} />;
  if (detailQuery.isError) return <ErrorState title="无法读取拼团" description={detailQuery.error.message} />;
  if (groupsQuery.isError) return <ErrorState title="无法读取谷团" description={groupsQuery.error.message} />;
  if (!activeGroupId) {
    return (
      <ErrorState
        title="缺少谷团上下文"
        description="新建拼团需要从谷团详情页进入。"
        action={<Link className="btn btn-primary" to="/app/groups">返回谷团</Link>}
      />
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <PageHeader
        action={<Link className="btn btn-secondary" params={{ groupId: activeGroupId }} to="/app/groups/$groupId">返回谷团</Link>}
        description={groupName ? `当前谷团：${groupName}` : undefined}
        title={groupBuyId ? "编辑拼团" : "新建拼团"}
      />

      <Surface className="p-5">
        <div className="space-y-4">
          <TextInput
            className="border-0 border-b border-slate-200 px-0 text-base font-semibold shadow-none focus:border-cyan-600 focus:ring-0"
            onChange={(event) => updateForm({ title: event.target.value })}
            placeholder="填写拼团标题"
            value={form.title}
          />
          <TextArea
            className="min-h-36 resize-y border-0 px-0 shadow-none focus:ring-0"
            onChange={(event) => updateForm({ description: event.target.value })}
            placeholder="填写拼团的规则和内容"
            value={form.description}
          />
          <MultiImageUploader images={coverImages} onAdd={addCoverFiles} onRemove={removeCoverImage} />
        </div>
      </Surface>

      <SectionLabel>谷子设置</SectionLabel>
      <SettingPanel>
        <SettingRow label="拼谷类型">
          <Segmented onChange={(value) => updateForm({ claimMode: value })} options={claimModes} value={form.claimMode} />
        </SettingRow>
        <SettingRow label="能否撤排">
          <Segmented
            onChange={(value) => updateForm({ canCancelClaim: value === "可撤排" })}
            options={["可撤排", "不可撤排"]}
            value={form.canCancelClaim ? "可撤排" : "不可撤排"}
          />
        </SettingRow>
        <SettingRow className="relative" label="谷子种类" onClick={() => setItemsExpanded((value) => !value)}>
          <div className="flex min-w-0 items-center gap-2 text-right text-sm text-slate-500">
            {firstItem ? (
              <span className="max-w-48 truncate">{firstItem.name || "未命名谷子"}</span>
            ) : (
              <span>请添加谷子</span>
            )}
            {itemsExpanded ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
          </div>
          {!itemsExpanded && hiddenItemCount > 0 ? (
            <span className="absolute bottom-1.5 right-9 text-[11px] font-semibold text-cyan-600">+{hiddenItemCount}</span>
          ) : null}
        </SettingRow>
      </SettingPanel>

      {itemsExpanded ? (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 sm:p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => setImportOpen(true)} type="button" variant="secondary">
                <Library className="size-4" />
                商品库导入
              </Button>
              <Button onClick={() => setEditingItem(emptyEditableItem())} type="button" variant="secondary">
                <PackagePlus className="size-4" />
                添加谷子
              </Button>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                className={cn(
                  "inline-flex min-h-10 items-center gap-2 rounded-md px-3.5 py-2 text-sm font-semibold transition",
                  equalPriceEnabled ? "bg-cyan-600 text-white" : "bg-slate-200 text-slate-600 hover:bg-slate-300",
                )}
                onClick={toggleEqualPrice}
                type="button"
              >
                均价
              </button>
              {equalPriceEnabled ? (
                <TextInput
                  className="w-32"
                  inputMode="decimal"
                  onChange={(event) => setEqualPrice(event.target.value)}
                  placeholder="均价"
                  value={equalPrice}
                />
              ) : null}
            </div>
          </div>

          {deleteWarning ? (
            <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              {deleteWarning}
            </div>
          ) : null}

          <div className="mt-4 space-y-3">
            {items.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
                还没有谷子，先从商品库导入或添加一个新 item。
              </div>
            ) : null}
            {items.map((item) => (
              <ItemCard
                equalPrice={equalPrice}
                equalPriceEnabled={equalPriceEnabled}
                item={item}
                key={item.localId}
                onCopy={() => copyItem(item)}
                onDelete={() => deleteItem(item)}
                onEdit={() => setEditingItem(item)}
              />
            ))}
            {items.length > 0 ? <div className="py-2 text-center text-sm text-slate-500">没有更多了</div> : null}
          </div>
        </div>
      ) : null}

      <SectionLabel>活动设置</SectionLabel>
      <SettingPanel>
        <SettingRow label="业务类型">
          <SelectInput
            className="w-36"
            onChange={(event) => updateForm({ groupBuyType: event.target.value })}
            value={form.groupBuyType}
          >
            {groupBuyTypes.map((type) => <option key={type}>{type}</option>)}
          </SelectInput>
        </SettingRow>
        <SettingRow label="开始时间">
          <TextInput
            className="w-52"
            onChange={(event) => updateForm({ startAt: event.target.value })}
            type="datetime-local"
            value={form.startAt}
          />
        </SettingRow>
        <SettingRow label="结束时间">
          <TextInput
            className="w-52"
            onChange={(event) => updateForm({ closeAt: event.target.value })}
            type="datetime-local"
            value={form.closeAt}
          />
        </SettingRow>
      </SettingPanel>

      <SectionLabel>售卖方式</SectionLabel>
      <SettingPanel>
        <SettingRow label="交易流程">
          <Segmented onChange={(value) => updateForm({ saleMode: value })} options={saleModes} value={form.saleMode} />
        </SettingRow>
      </SettingPanel>

      <SectionLabel>转单设置</SectionLabel>
      <SettingPanel>
        <SettingRow label="允许团员转单">
          <Toggle checked={form.allowTransfer} onChange={(value) => updateForm({ allowTransfer: value })} />
        </SettingRow>
      </SettingPanel>

      <SectionLabel>高级设置</SectionLabel>
      <SettingPanel>
        <SettingRow label="开启活动参与提醒">
          <Toggle checked={form.remindBeforeStart} onChange={(value) => updateForm({ remindBeforeStart: value })} />
        </SettingRow>
        <SettingRow label="显示参与人数">
          <Toggle checked={form.showParticipantCount} onChange={(value) => updateForm({ showParticipantCount: value })} />
        </SettingRow>
        <SettingRow label="显示总子余量">
          <Toggle checked={form.showTotalAmount} onChange={(value) => updateForm({ showTotalAmount: value })} />
        </SettingRow>
        <SettingRow label="显示谷子已排数量">
          <Toggle checked={form.showClaimedQuantity} onChange={(value) => updateForm({ showClaimedQuantity: value })} />
        </SettingRow>
      </SettingPanel>

      {save.error ? <ErrorState title="保存失败" description={formatSaveError(save.error)} /> : null}

      <div className="sticky bottom-20 z-20 flex justify-end gap-2 rounded-lg border border-slate-200 bg-white/90 p-3 shadow-lg backdrop-blur md:bottom-4">
        <Button onClick={() => setForm(initialForm)} type="button" variant="secondary">重置</Button>
        <Button busy={save.isPending} onClick={() => save.mutate()} type="button">
          <Upload className="size-4" />
          保存拼团
        </Button>
      </div>

      <ItemEditorModal
        currentUser={currentMember}
        equalPrice={equalPrice}
        equalPriceEnabled={equalPriceEnabled}
        groupId={activeGroupId}
        item={editingItem}
        onClose={() => setEditingItem(null)}
        onSave={upsertItem}
      />
      <GoodsImportModal
        onAdd={(goodsItems) => {
          setItems((current) => [...current, ...goodsItems.map(itemFromGoods)]);
          setItemsExpanded(true);
          setImportOpen(false);
        }}
        onClose={() => setImportOpen(false)}
        open={importOpen}
      />
    </div>
  );
}
