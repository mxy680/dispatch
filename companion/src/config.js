import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const CONFIG_DIR = path.join(os.homedir(), ".dispatch-companion");
const CONFIG_FILE = path.join(CONFIG_DIR, "config.json");

function ensureDir() {
  if (!fs.existsSync(CONFIG_DIR)) {
    fs.mkdirSync(CONFIG_DIR, { recursive: true });
  }
}

export function loadConfig() {
  ensureDir();
  if (!fs.existsSync(CONFIG_FILE)) return {};
  return JSON.parse(fs.readFileSync(CONFIG_FILE, "utf-8"));
}

export function saveConfig(data) {
  ensureDir();
  const existing = loadConfig();
  const merged = { ...existing, ...data };
  fs.writeFileSync(CONFIG_FILE, JSON.stringify(merged, null, 2));
  return merged;
}

export function getDeviceToken() {
  return loadConfig().deviceToken ?? null;
}

export function getDeviceId() {
  return loadConfig().deviceId ?? null;
}

export function getBackendUrl() {
  return loadConfig().backendUrl ?? "http://localhost:8000";
}

export function resetConfig() {
  try {
    if (fs.existsSync(CONFIG_FILE)) fs.unlinkSync(CONFIG_FILE);
  } catch {
    // ignore
  }
}
