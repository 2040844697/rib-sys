import { useSyncExternalStore } from "react";

import { api, ApiError } from "@/lib/api";
import {
  clearSessionToken,
  getSessionToken,
  setSessionToken,
} from "@/lib/session";
import type { BootstrapResponse, CurrentUser, LoginRequest } from "@/types";

type AuthStatus = "idle" | "loading" | "authenticated" | "anonymous";

interface AuthSnapshot {
  status: AuthStatus;
  user: CurrentUser | null;
  capabilities: string[];
  defaultGroupId: string | null;
}

const anonymousState: AuthSnapshot = {
  status: "anonymous",
  user: null,
  capabilities: [],
  defaultGroupId: null,
};

class AuthStore {
  private snapshot: AuthSnapshot = {
    status: "idle",
    user: null,
    capabilities: [],
    defaultGroupId: null,
  };

  private bootstrapPromise: Promise<BootstrapResponse | null> | null = null;

  private listeners = new Set<() => void>();

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = () => this.snapshot;

  private emit() {
    for (const listener of this.listeners) {
      listener();
    }
  }

  private setSnapshot(next: AuthSnapshot) {
    this.snapshot = next;
    this.emit();
  }

  async bootstrap(force = false) {
    const sessionToken = getSessionToken();
    if (!sessionToken) {
      this.setSnapshot(anonymousState);
      return null;
    }

    if (this.bootstrapPromise && !force) {
      return this.bootstrapPromise;
    }

    this.setSnapshot({
      ...this.snapshot,
      status: "loading",
    });

    this.bootstrapPromise = api
      .bootstrap()
      .then((data) => {
        this.setSnapshot({
          status: "authenticated",
          user: data.currentUser,
          capabilities: data.capabilities,
          defaultGroupId: data.defaultGroupId,
        });
        return data;
      })
      .catch((error) => {
        clearSessionToken();
        this.setSnapshot(anonymousState);

        if (error instanceof ApiError && error.status === 401) {
          return null;
        }

        throw error;
      })
      .finally(() => {
        this.bootstrapPromise = null;
      });

    return this.bootstrapPromise;
  }

  async login(payload: LoginRequest) {
    const result = await api.login(payload);
    setSessionToken(result.sessionToken);
    await this.bootstrap(true);
    return result;
  }

  async logout() {
    try {
      await api.logout();
    } finally {
      clearSessionToken();
      this.setSnapshot(anonymousState);
    }
  }

  updateUser(patch: Partial<CurrentUser>) {
    if (!this.snapshot.user) {
      return;
    }

    this.setSnapshot({
      ...this.snapshot,
      user: {
        ...this.snapshot.user,
        ...patch,
      },
    });
  }
}

export const authStore = new AuthStore();

export function useAuthState() {
  return useSyncExternalStore(authStore.subscribe, authStore.getSnapshot);
}
