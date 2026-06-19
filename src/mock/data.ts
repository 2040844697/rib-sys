import type {
  AdminCapabilitiesResponse,
  BootstrapResponse,
  ClaimGroupBuyPayload,
  ClaimGroupBuyResponse,
  CurrentUser,
  GroupBuyCreatePayload,
  GroupBuyCreateResponse,
  GroupBuyDetailResponse,
  GroupBuysResponse,
  GroupHomeResponse,
  GroupsResponse,
  MeResponse,
  UpdateMePayload,
  UserRole,
} from "@/types";

interface GroupEntity {
  id: string;
  name: string;
  description: string;
  coverImageUrl: string | null;
  leaderId: string;
  memberCount: number;
}

interface GroupBuyEntity {
  id: string;
  groupId: string;
  title: string;
  type: string;
  status: string;
  description: string;
  closeAt: string;
  coverImageUrl: string | null;
}

interface GroupBuyItemEntity {
  id: string;
  groupBuyId: string;
  name: string;
  characterName: string;
  imageUrl: string | null;
  unitPriceCny: string;
  totalQuantity: number;
}

interface GroupBuyRecordEntity {
  id: string;
  ownerId: string;
  groupBuyId: string;
  groupBuyItemId: string;
  quantity: number;
  displayStatus: string;
  isException: boolean;
}

const users = new Map<string, CurrentUser>([
  [
    "user_member",
    {
      id: "user_member",
      account: "member",
      displayName: "成员A",
      qqNumber: "123456",
      groupNickname: "A昵称",
      roles: ["member"],
    },
  ],
  [
    "user_maintainer",
    {
      id: "user_maintainer",
      account: "maintainer",
      displayName: "维护人小满",
      qqNumber: "223344",
      groupNickname: "小满",
      roles: ["member", "group_buy_maintainer"],
    },
  ],
  [
    "user_stock",
    {
      id: "user_stock",
      account: "stock",
      displayName: "囤货人阿简",
      qqNumber: "334455",
      groupNickname: "阿简",
      roles: ["member", "stock_keeper"],
    },
  ],
  [
    "user_admin",
    {
      id: "user_admin",
      account: "admin",
      displayName: "管理员莓莓",
      qqNumber: "445566",
      groupNickname: "莓莓",
      roles: ["member", "group_buy_maintainer", "stock_keeper", "admin"],
    },
  ],
]);

const groups: GroupEntity[] = [
  {
    id: "group_1",
    name: "月海谷仓",
    description: "第一版移动端优先体验团，用于验证拼团、付款和排发流程。",
    coverImageUrl: null,
    leaderId: "user_admin",
    memberCount: 42,
  },
  {
    id: "group_2",
    name: "星砂拼团局",
    description: "轻量测试团，保留一组简洁数据用于空状态和长文本验证。",
    coverImageUrl: null,
    leaderId: "user_maintainer",
    memberCount: 18,
  },
];

const groupBuys: GroupBuyEntity[] = [
  {
    id: "gb_1",
    groupId: "group_1",
    title: "月岛生日吧唧团",
    type: "群内开谷",
    status: "拼拼拼",
    description: "第一批主推拼团，含吧唧、色纸和拍立得。",
    closeAt: "2026-06-30T12:00:00+08:00",
    coverImageUrl: null,
  },
  {
    id: "gb_2",
    groupId: "group_1",
    title: "夏日拍立得补尾款",
    type: "补款",
    status: "等待开团",
    description: "尚未开启的补款拼团，用于测试未开始状态。",
    closeAt: "2026-07-02T18:00:00+08:00",
    coverImageUrl: null,
  },
  {
    id: "gb_3",
    groupId: "group_1",
    title: "夜航票夹加印",
    type: "现货加开",
    status: "已截团",
    description: "已截止的票夹加印拼团。",
    closeAt: "2026-06-16T23:59:00+08:00",
    coverImageUrl: null,
  },
  {
    id: "gb_4",
    groupId: "group_1",
    title: "周年亚克力补寄",
    type: "补寄",
    status: "已完成",
    description: "已完成的补寄拼团样例。",
    closeAt: "2026-05-20T20:00:00+08:00",
    coverImageUrl: null,
  },
  {
    id: "gb_5",
    groupId: "group_2",
    title: "星砂透卡试运行",
    type: "群内开谷",
    status: "已取消",
    description: "预留给第二个谷团的取消状态示例。",
    closeAt: "2026-06-28T14:00:00+08:00",
    coverImageUrl: null,
  },
];

const groupBuyItems: GroupBuyItemEntity[] = [
  {
    id: "gbi_1",
    groupBuyId: "gb_1",
    name: "月岛吧唧",
    characterName: "月岛萤",
    imageUrl: null,
    unitPriceCny: "35.00",
    totalQuantity: 20,
  },
  {
    id: "gbi_2",
    groupBuyId: "gb_1",
    name: "海报色纸",
    characterName: "影山飞雄",
    imageUrl: null,
    unitPriceCny: "28.00",
    totalQuantity: 16,
  },
  {
    id: "gbi_3",
    groupBuyId: "gb_1",
    name: "拍立得两连",
    characterName: "及川彻",
    imageUrl: null,
    unitPriceCny: "42.00",
    totalQuantity: 12,
  },
  {
    id: "gbi_4",
    groupBuyId: "gb_2",
    name: "夏日拍立得",
    characterName: "孤爪研磨",
    imageUrl: null,
    unitPriceCny: "18.00",
    totalQuantity: 40,
  },
  {
    id: "gbi_5",
    groupBuyId: "gb_3",
    name: "夜航票夹",
    characterName: "赤苇京治",
    imageUrl: null,
    unitPriceCny: "25.00",
    totalQuantity: 15,
  },
];

const groupBuyRecords: GroupBuyRecordEntity[] = [
  {
    id: "record_1",
    ownerId: "user_member",
    groupBuyId: "gb_1",
    groupBuyItemId: "gbi_1",
    quantity: 1,
    displayStatus: "未肾",
    isException: false,
  },
  {
    id: "record_2",
    ownerId: "user_maintainer",
    groupBuyId: "gb_1",
    groupBuyItemId: "gbi_2",
    quantity: 2,
    displayStatus: "未补国际",
    isException: false,
  },
  {
    id: "record_3",
    ownerId: "guest_1",
    groupBuyId: "gb_1",
    groupBuyItemId: "gbi_1",
    quantity: 5,
    displayStatus: "未到货",
    isException: false,
  },
  {
    id: "record_4",
    ownerId: "guest_2",
    groupBuyId: "gb_1",
    groupBuyItemId: "gbi_3",
    quantity: 4,
    displayStatus: "可排发",
    isException: false,
  },
  {
    id: "record_5",
    ownerId: "user_stock",
    groupBuyId: "gb_3",
    groupBuyItemId: "gbi_5",
    quantity: 1,
    displayStatus: "已申请排发",
    isException: false,
  },
];

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function getUserBySession(sessionToken: string | null) {
  if (!sessionToken) {
    return null;
  }

  return users.get(sessionToken) ?? null;
}

export function getUserByAccount(account: string) {
  return Array.from(users.values()).find((item) => item.account === account) ?? null;
}

export function getUserBySessionToken(sessionToken: string | null) {
  return getUserBySession(sessionToken);
}

function hasRole(user: CurrentUser, expected: UserRole | UserRole[]) {
  const roles = Array.isArray(expected) ? expected : [expected];
  return roles.some((role) => user.roles.includes(role));
}

function getAppCapabilities(user: CurrentUser) {
  const capabilities = ["group:view", "group_buy:view", "record:create_self"];

  if (hasRole(user, ["group_buy_maintainer", "admin"])) {
    capabilities.push("group_buy:create", "group_buy:edit", "record:manage");
  }

  if (hasRole(user, ["stock_keeper", "admin"])) {
    capabilities.push("warehouse:view", "dispatch:manage");
  }

  if (hasRole(user, "admin")) {
    capabilities.push("group:edit", "member:manage", "audit:view");
  }

  return capabilities;
}

function getLeaderName(group: GroupEntity) {
  return users.get(group.leaderId)?.displayName ?? "团长";
}

function isActiveGroupBuy(status: string) {
  return status === "拼拼拼" || status === "已切";
}

function matchesStatusFilter(filter: string | null, status: string) {
  if (!filter || filter === "全部") {
    return true;
  }

  if (filter === "进行中") {
    return status === "拼拼拼" || status === "已切";
  }

  if (filter === "未开始") {
    return status === "等待开团";
  }

  return filter === status;
}

function getClaimedQuantity(groupBuyItemId: string) {
  return groupBuyRecords
    .filter((item) => item.groupBuyItemId === groupBuyItemId)
    .reduce((total, item) => total + item.quantity, 0);
}

function getGroupBuyItemsForList(groupBuyId: string) {
  return groupBuyItems.filter((item) => item.groupBuyId === groupBuyId);
}

function getMyRecords(groupBuyId: string, userId: string) {
  return groupBuyRecords.filter(
    (item) => item.groupBuyId === groupBuyId && item.ownerId === userId,
  );
}

export function buildBootstrap(user: CurrentUser): BootstrapResponse {
  return {
    currentUser: clone(user),
    defaultGroupId: "group_1",
    capabilities: getAppCapabilities(user),
  };
}

export function buildGroups(user: CurrentUser): GroupsResponse {
  return {
    items: groups.map((group) => ({
      id: group.id,
      name: group.name,
      coverImageUrl: group.coverImageUrl,
      memberCount: group.memberCount,
      activeGroupBuyCount: groupBuys.filter(
        (item) => item.groupId === group.id && isActiveGroupBuy(item.status),
      ).length,
      myRoles: clone(user.roles),
    })),
  };
}

export function buildGroupHome(
  groupId: string,
  user: CurrentUser,
): GroupHomeResponse | null {
  const group = groups.find((item) => item.id === groupId);
  if (!group) {
    return null;
  }

  const pendingPaymentCount = groupBuyRecords.filter(
    (item) => item.ownerId === user.id && item.displayStatus === "未肾",
  ).length;

  const dispatchableCount = groupBuyRecords.filter(
    (item) => item.ownerId === user.id && item.displayStatus === "可排发",
  ).length;

  return {
    group: {
      id: group.id,
      name: group.name,
      description: group.description,
      coverImageUrl: group.coverImageUrl,
      leader: {
        id: group.leaderId,
        displayName: getLeaderName(group),
      },
      memberCount: group.memberCount,
      myRoles: clone(user.roles),
    },
    capabilities: {
      canEditGroup: hasRole(user, "admin"),
      canEnterAdmin: hasRole(user, ["group_buy_maintainer", "stock_keeper", "admin"]),
      canCreateGroupBuy: hasRole(user, ["group_buy_maintainer", "admin"]),
    },
    summary: {
      activeGroupBuyCount: groupBuys.filter(
        (item) => item.groupId === group.id && isActiveGroupBuy(item.status),
      ).length,
      myPendingPaymentCount: pendingPaymentCount,
      myDispatchableCount: dispatchableCount,
    },
  };
}

export function buildGroupBuys(
  groupId: string,
  user: CurrentUser,
  filters: { status: string | null; keyword: string | null },
): GroupBuysResponse {
  const keyword = filters.keyword?.trim().toLowerCase() ?? "";

  const items = groupBuys
    .filter((item) => item.groupId === groupId)
    .filter((item) => matchesStatusFilter(filters.status, item.status))
    .filter((item) => {
      if (!keyword) {
        return true;
      }

      return (
        item.title.toLowerCase().includes(keyword) ||
        item.type.toLowerCase().includes(keyword)
      );
    })
    .map((item) => {
      const itemsInBuy = getGroupBuyItemsForList(item.id);
      const myRecordCount = getMyRecords(item.id, user.id).reduce(
        (total, record) => total + record.quantity,
        0,
      );

      return {
        id: item.id,
        title: item.title,
        type: item.type,
        status: item.status,
        closeAt: item.closeAt,
        itemCount: itemsInBuy.length,
        availableQuantity: itemsInBuy.reduce(
          (total, entry) => total + (entry.totalQuantity - getClaimedQuantity(entry.id)),
          0,
        ),
        myRecordCount,
        coverImageUrl: item.coverImageUrl,
      };
    });

  return {
    items,
    total: items.length,
  };
}

export function buildAdminCapabilities(
  user: CurrentUser,
): AdminCapabilitiesResponse {
  const modules = [
    {
      key: "group_buys",
      title: "拼团管理",
      description: "新建、编辑和查看拼团",
      enabled: hasRole(user, ["group_buy_maintainer", "admin"]),
    },
    {
      key: "records",
      title: "拼单记录",
      description: "查看成员认领和状态流转",
      enabled: hasRole(user, ["group_buy_maintainer", "admin"]),
    },
    {
      key: "payments",
      title: "费用付款",
      description: "维护尾款、国际费和付款状态",
      enabled: hasRole(user, ["group_buy_maintainer", "admin"]),
    },
    {
      key: "warehouse",
      title: "囤货排发",
      description: "入库、排发和国内快递",
      enabled: hasRole(user, ["stock_keeper", "admin"]),
    },
    {
      key: "audit",
      title: "审计日志",
      description: "查看异常和角色变更记录",
      enabled: hasRole(user, "admin"),
    },
  ];

  return { modules };
}

export function buildGroupBuyDetail(
  groupBuyId: string,
  user: CurrentUser,
): GroupBuyDetailResponse | null {
  const groupBuy = groupBuys.find((item) => item.id === groupBuyId);
  if (!groupBuy) {
    return null;
  }

  const items = getGroupBuyItemsForList(groupBuyId).map((item) => {
    const claimedQuantity = getClaimedQuantity(item.id);
    return {
      id: item.id,
      name: item.name,
      characterName: item.characterName,
      imageUrl: item.imageUrl,
      unitPriceCny: item.unitPriceCny,
      totalQuantity: item.totalQuantity,
      claimedQuantity,
      availableQuantity: item.totalQuantity - claimedQuantity,
      status: item.totalQuantity - claimedQuantity > 0 ? "可拼" : "已满",
    };
  });

  return {
    groupBuy: clone(groupBuy),
    items,
    myRecords: getMyRecords(groupBuyId, user.id).map((item) => ({
      id: item.id,
      groupBuyItemId: item.groupBuyItemId,
      quantity: item.quantity,
      displayStatus: item.displayStatus,
      isException: item.isException,
    })),
    capabilities: {
      canClaim:
        (groupBuy.status === "拼拼拼" || groupBuy.status === "已切") &&
        !hasRole(user, "stock_keeper"),
      canEdit: hasRole(user, ["group_buy_maintainer", "admin"]),
      canUploadOrderScreenshot: hasRole(user, ["group_buy_maintainer", "admin"]),
      canManageRecords: hasRole(user, ["group_buy_maintainer", "admin"]),
    },
  };
}

export function claimGroupBuyItem(
  payload: ClaimGroupBuyPayload,
  user: CurrentUser,
): ClaimGroupBuyResponse {
  const detail = buildGroupBuyDetail(payload.groupBuyId, user);
  if (!detail) {
    throw new Error("拼团不存在");
  }

  if (!detail.capabilities.canClaim) {
    throw new Error("当前角色暂时不能认领");
  }

  const item = detail.items.find((entry) => entry.id === payload.groupBuyItemId);
  if (!item) {
    throw new Error("拼团商品不存在");
  }

  const quantity = Math.floor(payload.quantity);
  if (quantity <= 0) {
    throw new Error("认领数量必须大于 0");
  }

  if (quantity > item.availableQuantity) {
    throw new Error("可认领数量不足");
  }

  const existingRecord = groupBuyRecords.find(
    (record) =>
      record.ownerId === user.id &&
      record.groupBuyId === payload.groupBuyId &&
      record.groupBuyItemId === payload.groupBuyItemId,
  );

  if (existingRecord) {
    existingRecord.quantity += quantity;
    existingRecord.displayStatus = "未肾";
    return {
      recordId: existingRecord.id,
      displayStatus: existingRecord.displayStatus,
    };
  }

  const nextId = `record_${groupBuyRecords.length + 1}`;
  groupBuyRecords.push({
    id: nextId,
    ownerId: user.id,
    groupBuyId: payload.groupBuyId,
    groupBuyItemId: payload.groupBuyItemId,
    quantity,
    displayStatus: "未肾",
    isException: false,
  });

  return {
    recordId: nextId,
    displayStatus: "未肾",
  };
}

export function createGroupBuy(
  payload: GroupBuyCreatePayload,
  user: CurrentUser,
): GroupBuyCreateResponse {
  if (!hasRole(user, ["group_buy_maintainer", "admin"])) {
    throw new Error("当前账号没有创建拼团的权限");
  }

  const nextId = `gb_${groupBuys.length + 1}`;
  groupBuys.unshift({
    id: nextId,
    groupId: payload.groupId,
    title: payload.title,
    type: payload.type,
    status: "等待开团",
    description: payload.description,
    closeAt: payload.closeAt,
    coverImageUrl: null,
  });

  return {
    groupBuyId: nextId,
  };
}

export function readMe(user: CurrentUser): MeResponse {
  return clone(user);
}

export function updateMe(user: CurrentUser, payload: UpdateMePayload): MeResponse {
  const target = users.get(user.id);
  if (!target) {
    throw new Error("用户不存在");
  }

  target.displayName = payload.displayName;
  target.groupNickname = payload.groupNickname;

  return clone(target);
}
