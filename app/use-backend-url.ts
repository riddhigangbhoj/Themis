"use client";

import { useState, useEffect, useCallback } from "react";

const STORAGE_KEY = "themis-backend-url";
const DEFAULT_URL = "http://localhost:8000";

export function useBackendUrl() {
  const [backendUrl, setBackendUrl] = useState(DEFAULT_URL);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) setBackendUrl(stored);
  }, []);

  const updateUrl = useCallback((url: string) => {
    const trimmed = url.replace(/\/+$/, ""); // strip trailing slashes
    setBackendUrl(trimmed);
    if (trimmed) {
      localStorage.setItem(STORAGE_KEY, trimmed);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  return { backendUrl, updateUrl };
}
