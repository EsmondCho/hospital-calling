import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The DRF backend at api.hospcall.drtail.us mandates trailing slashes on every
  // resource URL. Next.js 16 strips trailing slashes by default and emits a
  // 308 redirect, which breaks POST/PATCH/DELETE through /api/proxy/* —
  // disable that behaviour so the proxy can forward the URL exactly as the
  // client sent it.
  skipTrailingSlashRedirect: true,
};

export default nextConfig;
