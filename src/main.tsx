import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";

import "@/index.css";
import { isMockEnabled } from "@/lib/runtime";
import { router } from "@/routes";

async function enableMocking() {
  if (isMockEnabled) {
    const { worker } = await import("@/mock/browser");
    await worker.start({
      onUnhandledRequest: "bypass",
    });
  }
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
    mutations: {
      retry: 0,
    },
  },
});

await enableMocking();

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </React.StrictMode>,
);
