function normalizeApiBase(raw: string | undefined): string {
  const value = raw?.trim() ?? "";
  if (!value) return "";

  const withProtocol = /^https?:\/\//i.test(value) ? value : `https://${value}`;
  const url = new URL(withProtocol);
  if (url.pathname === "/api" || url.pathname === "/api/") {
    url.pathname = "/";
  }
  url.search = "";
  url.hash = "";
  return url.toString().replace(/\/+$/, "");
}

const rawApiBase = import.meta.env.VITE_API_BASE_URL ?? import.meta.env.VITE_BACKEND_URL;

export const env = {
  apiBase: normalizeApiBase(rawApiBase),
  appTitle: import.meta.env.VITE_APP_TITLE ?? "PowerGrid AI",
  appSubtitle: import.meta.env.VITE_APP_SUBTITLE ?? "Plant Intelligence Agent",
};
