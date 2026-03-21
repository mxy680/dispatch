import { app as electronApp, BrowserWindow, ipcMain, dialog } from "electron";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { startBridge } from "../src/bridge.js";
import { startWorker } from "../src/worker.js";
import { pairDevice } from "../src/pair.js";
import { loadConfig } from "../src/config.js";
import { resetConfig } from "../src/config.js";
import { getMyProjectLinks, linkProjectByName, getDeviceProjectBasePath, setDeviceProjectBasePath } from "../src/api.js";
import { execSync } from "node:child_process";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function readPackageMeta() {
  try {
    const pkgPath = path.join(__dirname, "..", "package.json");
    const raw = fs.readFileSync(pkgPath, "utf-8");
    const pkg = JSON.parse(raw);
    return { name: pkg.name ?? "dispatch-companion", version: pkg.version ?? "0.0.0" };
  } catch {
    return { name: "dispatch-companion", version: "0.0.0" };
  }
}

let mainWindow;
let workerStarted = false;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 980,
    height: 720,
    minWidth: 880,
    minHeight: 650,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const indexPath = path.join(__dirname, "renderer", "index.html");
  mainWindow.loadFile(indexPath);
}

ipcMain.handle("dispatch.get-config", async () => {
  return loadConfig();
});

ipcMain.handle("dispatch.get-app-info", async () => readPackageMeta());

ipcMain.handle("dispatch.pair-device", async (_event, { backendUrl, pairingCode }) => {
  if (!backendUrl || !String(backendUrl).trim()) throw new Error("backendUrl is required");
  if (!pairingCode || !String(pairingCode).trim()) throw new Error("pairingCode is required");
  const result = await pairDevice(String(backendUrl).trim(), String(pairingCode).trim());
  if (!workerStarted) workerStarted = startWorker();
  return result;
});

ipcMain.handle("dispatch.select-project-directory", async () => {
  const result = await dialog.showOpenDialog({
    properties: ["openDirectory"],
    title: "Select project folder",
  });
  if (result.canceled) return null;
  if (!result.filePaths?.[0]) return null;
  return result.filePaths[0];
});

ipcMain.handle("dispatch.link-project", async (_event, { projectName, localPath }) => {
  if (!projectName || !String(projectName).trim()) throw new Error("projectName is required");
  if (!localPath || !String(localPath).trim()) throw new Error("localPath is required");
  return linkProjectByName(String(projectName).trim(), String(localPath).trim());
});

ipcMain.handle("dispatch.get-linked-projects", async () => {
  const result = await getMyProjectLinks();
  return result?.links ?? [];
});

ipcMain.handle("dispatch.get-project-base-path", async () => {
  const result = await getDeviceProjectBasePath();
  return result?.base_path ?? null;
});

ipcMain.handle("dispatch.set-project-base-path", async (_event, { basePath }) => {
  const result = await setDeviceProjectBasePath(basePath);
  return result?.base_path ?? null;
});

ipcMain.handle("dispatch.open-cursor", async (_event, { folderPath }) => {
  if (!folderPath || !String(folderPath).trim()) throw new Error("folderPath is required");
  const fp = String(folderPath).trim().replace(/"/g, '\\"');
  try {
    // Try calling cursor directly (if Cursor is available on PATH for this app).
    try {
      const resolved = execSync("command -v cursor 2>/dev/null || which cursor 2>/dev/null", {
        stdio: "pipe",
        shell: true,
      })
        .toString()
        .trim();

      if (resolved) {
        execSync(`${resolved} "${fp}"`, { stdio: "ignore", shell: true });
        return { success: true };
      }
    } catch {
      // ignore; we'll fallback to `open -a`
    }

    // macOS fallback: open the Cursor app with the folder.
    const candidates = ["Cursor", "Cursor.app"];
    for (const appName of candidates) {
      try {
        execSync(`open -a "${appName}" --args "${fp}"`, { stdio: "ignore", shell: true });
        return { success: true };
      } catch {
        // try next candidate
      }
    }

    throw new Error("Could not launch Cursor (no cursor binary and open -a failed)");
  } catch (err) {
    return { success: false, error: String(err?.message ?? err) };
  }
});

ipcMain.handle("dispatch.reset-connection", async () => {
  resetConfig();
  electronApp.relaunch();
  electronApp.exit(0);
  return { success: true };
});

electronApp.whenReady().then(() => {
  createWindow();
  // Start the background services (Express bridge + worker loop).
  startBridge();
  workerStarted = startWorker();
});

electronApp.on("window-all-closed", () => {
  if (process.platform !== "darwin") electronApp.quit();
});

