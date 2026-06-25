import { getSessionToken } from "@/lib/session";
import type {
  AdminCapabilitiesResponse,
  AuditLogItem,
  BootstrapResponse,
  ClaimGroupBuyPayload,
  CurrentUser,
  GoodsSearchResponse,
  GroupBuyCreatePayload,
  GroupBuyCreateResponse,
  GroupBuyDetailResponse,
  GroupBuysResponse,
  GroupHomeResponse,
  GroupsResponse,
  ListResponse,
  LoginRequest,
  LoginResponse,
  RegisterRequest,
  RegisterResponse,
  UpdateMePayload,
} from "@/types";

export class ApiError extends Error {
  status: number;
  code?: string;
  details?: unknown;
  payload: unknown;

  constructor(message: string, status: number, payload: unknown, code?: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
    this.code = code;
    this.details = details;
  }
}

function parseJson(rawText: string) {
  if (!rawText) {
    return null;
  }

  try {
    return JSON.parse(rawText) as unknown;
  } catch {
    return rawText;
  }
}

function withQuery(path: string, params: Record<string, string | number | undefined | null>) {
  const url = new URL(path, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  });
  return `${url.pathname}${url.search}`;
}

async function fetchJson<T>(path: string, init: RequestInit & { bodyJson?: unknown } = {}) {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");

  if (init.bodyJson !== undefined) {
    headers.set("Content-Type", "application/json");
  }

  const sessionToken = getSessionToken();
  if (sessionToken) {
    headers.set("X-Session-Token", sessionToken);
  }

  const response = await fetch(path, {
    ...init,
    headers,
    body: init.bodyJson === undefined ? init.body : JSON.stringify(init.bodyJson),
  });

  const rawText = await response.text();
  const payload = parseJson(rawText);

  if (!response.ok) {
    const message =
      typeof payload === "object" &&
      payload !== null &&
      "message" in payload &&
      typeof payload.message === "string"
        ? payload.message
        : response.status === 404
          ? "后端接口暂未接入"
          : "请求失败";

    const code =
      typeof payload === "object" &&
      payload !== null &&
      "code" in payload &&
      typeof payload.code === "string"
        ? payload.code
        : undefined;

    const details =
      typeof payload === "object" && payload !== null && "details" in payload
        ? payload.details
        : undefined;

    throw new ApiError(message, response.status, payload, code, details);
  }

  return payload as T;
}

export const api = {
  login(payload: LoginRequest) {
    return fetchJson<LoginResponse>("/api/auth/login", { method: "POST", bodyJson: payload });
  },
  register(payload: RegisterRequest) {
    return fetchJson<RegisterResponse>("/api/auth/register", {
      method: "POST",
      bodyJson: payload,
    });
  },
  logout() {
    return fetchJson<{ ok: true }>("/api/auth/logout", { method: "POST" });
  },
  bootstrap() {
    return fetchJson<BootstrapResponse>("/api/app/bootstrap");
  },
  getMe() {
    return fetchJson<CurrentUser>("/api/me");
  },
  updateMe(payload: UpdateMePayload) {
    return fetchJson<{ ok: true }>("/api/me", { method: "PATCH", bodyJson: payload });
  },
  getGroups() {
    return fetchJson<GroupsResponse>("/api/app/groups");
  },
  getGroupHome(groupId: string) {
    return fetchJson<GroupHomeResponse>(`/api/app/groups/${groupId}/home`);
  },
  getGroupBuys(groupId: string, params: { status?: string; keyword?: string; type?: string }) {
    return fetchJson<GroupBuysResponse>(
      withQuery(`/api/app/groups/${groupId}/group-buys`, params),
    );
  },
  getAdminCapabilities(groupId: string) {
    return fetchJson<AdminCapabilitiesResponse>(`/api/app/groups/${groupId}/admin-capabilities`);
  },
  getGroupBuyDetail(groupBuyId: string) {
    return fetchJson<GroupBuyDetailResponse>(`/api/app/group-buys/${groupBuyId}/detail`);
  },
  claimGroupBuy(payload: ClaimGroupBuyPayload) {
    return fetchJson<{ recordId: string; displayStatus: string }>("/api/group-buy-records", {
      method: "POST",
      bodyJson: payload,
    });
  },
  createGroupBuy(payload: GroupBuyCreatePayload) {
    return fetchJson<GroupBuyCreateResponse>("/api/group-buys", {
      method: "POST",
      bodyJson: payload,
    });
  },
  updateGroupBuy(groupBuyId: string, payload: Partial<GroupBuyCreatePayload>) {
    return fetchJson<{ ok?: true; groupBuyId?: string }>(`/api/group-buys/${groupBuyId}`, {
      method: "PATCH",
      bodyJson: payload,
    });
  },
  changeGroupBuyStatus(groupBuyId: string, payload: { status: string; reason: string }) {
    return fetchJson<{ ok?: true }>(`/api/group-buys/${groupBuyId}/status`, {
      method: "POST",
      bodyJson: payload,
    });
  },
  createGroupBuyItem(payload: Record<string, unknown>) {
    return fetchJson<{ groupBuyItemId: string }>("/api/group-buy-items", {
      method: "POST",
      bodyJson: payload,
    });
  },
  updateGroupBuyItem(groupBuyItemId: string, payload: Record<string, unknown>) {
    return fetchJson<{ ok?: true }>(`/api/group-buy-items/${groupBuyItemId}`, {
      method: "PATCH",
      bodyJson: payload,
    });
  },
  requestPriceAdjustment(payload: Record<string, unknown>) {
    return fetchJson<{ priceAdjustmentId?: string }>("/api/price-adjustments", {
      method: "POST",
      bodyJson: payload,
    });
  },
  addOrderScreenshot(payload: Record<string, unknown>) {
    return fetchJson<{ orderScreenshotId?: string }>("/api/order-screenshots", {
      method: "POST",
      bodyJson: payload,
    });
  },
  searchGoods(params: {
    keyword?: string;
    characterName?: string;
    seriesName?: string;
    status?: string;
    page?: number;
    pageSize?: number;
  }) {
    return fetchJson<GoodsSearchResponse>(withQuery("/api/goods", params));
  },
  getGoodsSnapshot(goodsId: string) {
    return fetchJson<Record<string, unknown>>(`/api/goods/${goodsId}/snapshot`);
  },
  createGoods(payload: Record<string, unknown>) {
    return fetchJson<{ goodsId: string }>("/api/goods", { method: "POST", bodyJson: payload });
  },
  updateGoods(goodsId: string, payload: Record<string, unknown>) {
    return fetchJson<{ goodsId: string; updatedFields?: string[] }>(`/api/goods/${goodsId}`, {
      method: "PATCH",
      bodyJson: payload,
    });
  },
  createInternationalBatch(payload: Record<string, unknown>) {
    return fetchJson<{ batchId?: string }>("/api/international-batches", {
      method: "POST",
      bodyJson: payload,
    });
  },
  listAuditLogs(params: Record<string, string | undefined>) {
    return fetchJson<ListResponse<AuditLogItem>>(withQuery("/api/audit-logs", params));
  },

  // The following API paths are front-end contract calls. If the current backend has
  // not mounted them yet, pages show a clear "interface pending" state from 404.
  getMyRecords() {
    return fetchJson<ListResponse<Record<string, unknown>>>("/api/app/me/records");
  },
  getMyCharges() {
    return fetchJson<ListResponse<Record<string, unknown>>>("/api/my/charges");
  },
  submitPaymentProof(chargeId: string, payload: Record<string, unknown>) {
    return fetchJson<{ proofId?: string }>(`/api/charges/${chargeId}/payment-proofs`, {
      method: "POST",
      bodyJson: payload,
    });
  },
  getPaymentChannels() {
    return fetchJson<ListResponse<Record<string, unknown>>>("/api/payment-channels");
  },
  createPaymentChannel(payload: Record<string, unknown>) {
    return fetchJson<{ paymentChannelId?: string }>("/api/payment-channels", {
      method: "POST",
      bodyJson: payload,
    });
  },
  getDispatchableItems() {
    return fetchJson<ListResponse<Record<string, unknown>>>("/api/my/dispatchable-items");
  },
  createDispatchRequest(payload: Record<string, unknown>) {
    return fetchJson<{ dispatchRequestId?: string }>("/api/dispatch-requests", {
      method: "POST",
      bodyJson: payload,
    });
  },
  getDispatchRequests() {
    return fetchJson<ListResponse<Record<string, unknown>>>("/api/dispatch-requests");
  },
  getTransferRequests() {
    return fetchJson<ListResponse<Record<string, unknown>>>("/api/transfers");
  },
  requestTransfer(payload: Record<string, unknown>) {
    return fetchJson<{ transferId?: string }>("/api/transfers", {
      method: "POST",
      bodyJson: payload,
    });
  },
  getExceptions() {
    return fetchJson<ListResponse<Record<string, unknown>>>("/api/exceptions");
  },
  getUsers() {
    return fetchJson<ListResponse<Record<string, unknown>>>("/api/users");
  },
  getAddresses() {
    return fetchJson<ListResponse<Record<string, unknown>>>("/api/me/addresses");
  },
  createAddress(payload: Record<string, unknown>) {
    return fetchJson<{ addressId?: string }>("/api/me/addresses", {
      method: "POST",
      bodyJson: payload,
    });
  },
};
