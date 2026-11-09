"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AppConfig } from "@/lib/types";

const ConfigContext = createContext<AppConfig | null>(null);

export function ConfigProvider({ children }: { children: React.ReactNode }) {
  const [config, setConfig] = useState<AppConfig | null>(null);
  useEffect(() => {
    api.config().then(setConfig, () => setConfig(null));
  }, []);
  return <ConfigContext.Provider value={config}>{children}</ConfigContext.Provider>;
}

export function useConfig() {
  return useContext(ConfigContext);
}
