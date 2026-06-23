export const isDevelopment = import.meta.env.DEV;
export const isMockEnabled = import.meta.env.VITE_ENABLE_MOCKS === "true";

export const runtimeModeLabel = isMockEnabled ? "Mock API" : "Backend API";
