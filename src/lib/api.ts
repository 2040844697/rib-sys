import { getSessionToken } from "@/lib/session";
import { isMockEnabled } from "@/lib/runtime";
import type {
  AdminCapabilitiesResponse,
  BootstrapResponse,
  ClaimGroupBuyPayload,
  ClaimGroupBuyResponse,
  GroupBuyCreatePayload,
  GroupBuyCreateResponse,
  GroupBuyDetailResponse,
  GroupBuysResponse,
  GroupHomeResponse,
  GroupsResponse,
  LoginRequest,
  LoginResponse,
  MeResponse,
  RegisterResponse,
  RegisterRequest,
  UpdateMePayload,
} from "@/types";

export class ApiError extends Error {
  status: number;
  code?: string;
  details?: unknown;
  payload: unknown;

  constructor(
    message: string,
    status: number,
    payload: unknown,
    code?: string,
    details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.payload = payload;
  }
}

function tryParseJson(rawText: string) {
  if (!rawText) {
    return null;
  }

  try {
    return JSON.parse(rawText) as unknown;
  } catch {
    return rawText;
  }
}

async function fetchJson<T>(
  path: string,
  init: RequestInit & { bodyJson?: unknown } = {},
) {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");

  if (init.bodyJson !== undefined) {
    headers.set("Content-Type", "application/json");
  }

  const sessionToken = getSessionToken();
  if (sessionToken) {
    headers.set("X-Session-Token", sessionToken);
    if (isMockEnabled) {
      headers.set("X-Mock-Session", sessionToken);
    }
  }

  const response = await fetch(path, {
    ...init,
    headers,
    body: init.bodyJson === undefined ? init.body : JSON.stringify(init.bodyJson),
  });

  const rawText = await response.text();
  const payload = tryParseJson(rawText);

  if (!response.ok) {
    const message =
      typeof payload === "object" &&
      payload !== null &&
      "message" in payload &&
      typeof payload.message === "string"
        ? payload.message
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
    return fetchJson<LoginResponse>("/api/auth/login", {
      method: "POST",
      bodyJson: payload,
    });
  },
  register(payload: RegisterRequest) {
    return fetchJson<RegisterResponse>("/api/auth/register", {
      method: "POST",
      bodyJson: payload,
    });
  },
  logout() {
    return fetchJson<{ ok: true }>("/api/auth/logout", {
      method: "POST",
    });
  },
  bootstrap() {
    return fetchJson<BootstrapResponse>("/api/app/bootstrap");
  },
  getGroups() {
    return fetchJson<GroupsResponse>("/api/app/groups");
  },
  getGroupHome(groupId: string) {
    return fetchJson<GroupHomeResponse>(`/api/app/groups/${groupId}/home`);
  },
  getGroupBuys(groupId: string, params: { status?: string; keyword?: string }) {
    const url = new URL(`/api/app/groups/${groupId}/group-buys`, window.location.origin);
    if (params.status) {
      url.searchParams.set("status", params.status);
    }
    if (params.keyword) {
      url.searchParams.set("keyword", params.keyword);
    }

    return fetchJson<GroupBuysResponse>(url.pathname + url.search);
  },
  getAdminCapabilities(groupId: string) {
    return fetchJson<AdminCapabilitiesResponse>(
      `/api/app/groups/${groupId}/admin-capabilities`,
    );
  },
  getGroupBuyDetail(groupBuyId: string) {
    return fetchJson<GroupBuyDetailResponse>(
      `/api/app/group-buys/${groupBuyId}/detail`,
    );
  },
  claimGroupBuy(payload: ClaimGroupBuyPayload) {
    return fetchJson<ClaimGroupBuyResponse>("/api/group-buy-records", {
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
  getMe() {
    return fetchJson<MeResponse>("/api/me");
  },
  updateMe(payload: UpdateMePayload) {
    return fetchJson<{ ok: true }>("/api/me", {
      method: "PATCH",
      bodyJson: payload,
    });
  },
};
