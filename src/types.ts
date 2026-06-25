export type UserRole = "member" | "group_buy_maintainer" | "stock_keeper" | "admin";

export interface CurrentUser {
  id: string;
  account?: string;
  displayName: string;
  qqNumber: string;
  groupNickname: string;
  roles: UserRole[];
  status?: string;
  groupId?: string;
}

export interface LoginRequest {
  account: string;
  password: string;
}

export interface LoginResponse {
  userId: string;
  displayName: string;
  roles: UserRole[];
  next: string;
  sessionToken: string;
  session?: {
    expiresAt: string;
  };
}

export interface RegisterRequest {
  displayName: string;
  qqNumber: string;
  groupNickname: string;
  password: string;
  confirmPassword: string;
}

export interface RegisterResponse {
  ok: true;
  userId?: string;
  canLoginNow?: boolean;
  nextAction?: "login" | "wait_review";
}

export interface BootstrapResponse {
  currentUser: CurrentUser;
  defaultGroupId: string;
  capabilities: string[];
}

export interface GroupSummaryItem {
  id: string;
  name: string;
  coverImageUrl: string | null;
  memberCount: number;
  activeGroupBuyCount: number;
  myRoles: UserRole[];
}

export interface GroupsResponse {
  items: GroupSummaryItem[];
}

export interface GroupHomeResponse {
  group: {
    id: string;
    name: string;
    description?: string | null;
    coverImageUrl: string | null;
    leader: {
      id: string | null;
      displayName: string;
    };
    memberCount: number;
    myRoles: UserRole[];
  };
  capabilities: {
    canEditGroup: boolean;
    canEnterAdmin: boolean;
    canCreateGroupBuy: boolean;
  };
  summary: {
    activeGroupBuyCount: number;
    myPendingPaymentCount: number;
    myDispatchableCount: number;
  };
}

export interface GroupBuyListItem {
  id: string;
  title: string;
  type: string;
  status: string;
  initiator?: {
    id?: string;
    displayName: string;
  };
  ownerName?: string;
  closeAt: string;
  itemCount: number;
  availableQuantity: number;
  myRecordCount: number;
  coverImageUrl: string | null;
}

export interface GroupBuysResponse {
  items: GroupBuyListItem[];
  total: number;
}

export interface AdminModule {
  key: string;
  title: string;
  description: string;
  enabled: boolean;
}

export interface AdminCapabilitiesResponse {
  modules: AdminModule[];
}

export interface GroupBuyItem {
  id: string;
  goodsId?: string | null;
  name: string;
  alias?: string | null;
  characterName?: string;
  characterNames?: string[];
  description?: string | null;
  imageUrl: string | null;
  unitPriceCny: string;
  weightGram?: number | null;
  estimatedWeightGram?: number | null;
  totalQuantity: number;
  claimedQuantity: number;
  reservedQuantity?: number;
  availableQuantity: number;
  status: string;
  note?: string | null;
}

export interface GroupBuyRecord {
  id: string;
  groupBuyItemId: string;
  quantity: number;
  displayStatus: string;
  isException: boolean;
}

export interface GroupBuyDetailResponse {
  groupBuy: {
    id: string;
    groupId: string;
    title: string;
    type: string;
    status: string;
    description?: string | null;
    closeAt: string;
    paymentChannelId?: string | null;
    stockKeeperUserId?: string | null;
  };
  items: GroupBuyItem[];
  myRecords: GroupBuyRecord[];
  capabilities: {
    canClaim: boolean;
    canEdit: boolean;
    canUploadOrderScreenshot: boolean;
    canManageRecords: boolean;
  };
}

export interface GoodsSummary {
  id: string;
  name: string;
  seriesName?: string | null;
  aliases?: string[];
  characterNames?: string[];
  sku?: string | null;
  description?: string | null;
  mainImageUrl?: string | null;
  weightGram?: number | null;
  domesticSpotSuggestedPriceCny?: string | null;
  status: string;
  imageCount?: number;
  updatedAt?: string;
}

export interface GoodsSearchResponse {
  items: GoodsSummary[];
  total: number;
  page?: number;
  pageSize?: number;
}

export interface AuditLogItem {
  id: string;
  actorUserId?: string | null;
  actorName?: string | null;
  action: string;
  objectType: string;
  objectId?: string | null;
  reason?: string | null;
  createdAt: string;
}

export interface ListResponse<T> {
  items: T[];
  total?: number;
}

export interface ClaimGroupBuyPayload {
  groupBuyId: string;
  groupBuyItemId: string;
  quantity: number;
}

export interface GroupBuyCreatePayload {
  groupId: string;
  type: string;
  title: string;
  description: string;
  closeAt: string;
  paymentChannelId?: string;
  defaultChannel?: string;
  defaultStockKeeper?: string;
}

export interface GroupBuyCreateResponse {
  groupBuyId: string;
}

export interface UpdateMePayload {
  displayName: string;
  groupNickname: string;
}
