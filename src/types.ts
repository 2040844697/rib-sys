export type UserRole =
  | "member"
  | "group_buy_maintainer"
  | "stock_keeper"
  | "admin";

export interface CurrentUser {
  id: string;
  account: string;
  displayName: string;
  qqNumber: string;
  groupNickname: string;
  roles: UserRole[];
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
    description: string;
    coverImageUrl: string | null;
    leader: {
      id: string;
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
  name: string;
  characterName: string;
  imageUrl: string | null;
  unitPriceCny: string;
  totalQuantity: number;
  claimedQuantity: number;
  availableQuantity: number;
  status: string;
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
    description: string;
    closeAt: string;
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

export interface ClaimGroupBuyPayload {
  groupBuyId: string;
  groupBuyItemId: string;
  quantity: number;
}

export interface ClaimGroupBuyResponse {
  recordId: string;
  displayStatus: string;
}

export interface UpdateMePayload {
  displayName: string;
  groupNickname: string;
}

export type MeResponse = CurrentUser;

export interface GroupBuyCreatePayload {
  groupId: string;
  type: string;
  title: string;
  description: string;
  closeAt: string;
  defaultChannel: string;
  defaultStockKeeper: string;
}

export interface GroupBuyCreateResponse {
  groupBuyId: string;
}
