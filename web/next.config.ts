import type { NextConfig } from "next";
import path from "node:path";
import { fileURLToPath } from "node:url";

// When the dev server or tooling runs with cwd above `web/`, CSS `@import "tailwindcss"`
// can otherwise resolve from the repo root (no local node_modules) and fail. Pin Turbopack
// to this app directory so packages resolve from `web/node_modules`.
const turbopackRoot =
  typeof import.meta.dirname === "string"
    ? import.meta.dirname
    : path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  turbopack: {
    root: turbopackRoot,
  },
};

export default nextConfig;
