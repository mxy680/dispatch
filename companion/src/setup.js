import readline from "node:readline";
import path from "node:path";
import fs from "node:fs";
import { execSync } from "node:child_process";
import { getBackendUrl, getDeviceToken, saveConfig, loadConfig } from "./config.js";
import { linkProjectByName } from "./api.js";

const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
function ask(question) {
  return new Promise((resolve) => rl.question(question, resolve));
}

async function request(method, urlPath, body = undefined) {
  const url = `${getBackendUrl()}${urlPath}`;
  const headers = { "Content-Type": "application/json" };
  const token = getDeviceToken();
  if (token) headers["X-Device-Token"] = token;
  const res = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`${method} ${urlPath} ${res.status}: ${json?.detail ?? res.statusText}`);
  return json;
}

function detectCursor() {
  const checks = ["command -v agent", "which agent", "agent --help", "agent --version", "cursor --version", "cursor --help"];
  for (const cmd of checks) {
    try {
      const out = execSync(cmd, { timeout: 5000, stdio: "pipe" }).toString().trim();
      if (out) return { found: true, output: out };
    } catch {
      continue;
    }
  }
  return { found: false, output: null };
}

export async function runSetup() {
  if (!getDeviceToken()) {
    console.error("[setup] Not paired yet. Run: node src/index.js pair <backend-url> <code>");
    process.exit(1);
  }

  console.log("\n--- Dispatch Companion Setup ---\n");

  const cursorStatus = detectCursor();
  let detectedAgentPath = null;
  try {
    const resolved = execSync("command -v agent", { timeout: 5000, stdio: "pipe" }).toString().trim();
    if (resolved) detectedAgentPath = resolved;
  } catch {
    detectedAgentPath = null;
  }
  if (cursorStatus.found) {
    console.log(`[setup] Cursor tooling detected: ${cursorStatus.output}`);
    if (detectedAgentPath) {
      console.log(`[setup] Resolved agent path: ${detectedAgentPath}`);
    }
  } else {
    console.log("[setup] Cursor tooling not found. Install Cursor and enable `agent` CLI in PATH.");
    console.log("        You can still use Claude or Shell providers.\n");
  }

  let result;
  try {
    result = await request("GET", "/api/device/my-projects");
  } catch (err) {
    console.error("[setup] Could not fetch project links:", err.message);
    rl.close();
    return;
  }
  const existingLinks = result?.links ?? [];

  if (existingLinks.length > 0) {
    console.log("\nCurrently linked projects:");
    for (const link of existingLinks) {
      const name = link.project_name || link.project_id;
      const lp = link.local_path || "(no local path set)";
      console.log(`  - ${name}  ->  ${lp}`);
    }
  }

  const addMore = await ask("\nLink a project folder? (y/n): ");
  if (addMore.trim().toLowerCase() !== "y") {
    console.log("[setup] Done.");
    rl.close();
    return;
  }

  const rawPath = (await ask("Local project folder (absolute path): ")).trim();
  const folderPath = rawPath.replace(/^['"]|['"]$/g, "");
  if (!folderPath || !path.isAbsolute(folderPath)) {
    console.error("[setup] Must be an absolute path.");
    rl.close();
    return;
  }
  if (!fs.existsSync(folderPath) || !fs.statSync(folderPath).isDirectory()) {
    console.error("[setup] Path does not exist or is not a directory.");
    rl.close();
    return;
  }

  const projectName = path.basename(folderPath);
  console.log(`[setup] Project name will be: "${projectName}"`);

  let projects;
  try {
    const userProjects = await request("GET", "/api/device/my-projects");
    projects = (userProjects?.links ?? []).map((l) => ({
      id: l.project_id,
      name: l.project_name,
    }));
  } catch {
    projects = [];
  }

  let projectId = null;
  const matching = projects.find((p) => p.name && p.name.toLowerCase() === projectName.toLowerCase());
  if (matching) {
    projectId = matching.id;
    console.log(`[setup] Found existing project "${matching.name}" (${projectId})`);
  }

  const config = loadConfig();
  const localProjects = config.localProjects ?? {};
  if (detectedAgentPath) {
    saveConfig({ agentPath: detectedAgentPath });
  }
  localProjects[projectName] = { path: folderPath, projectId: projectId || null };
  saveConfig({ localProjects });

  try {
    const linked = await linkProjectByName(projectName, folderPath);
    const linkedProjectId = linked?.project?.id ?? null;
    if (linkedProjectId) {
      localProjects[projectName] = { path: folderPath, projectId: linkedProjectId };
      saveConfig({ localProjects });
      console.log(`[setup] Linked to backend: project "${projectName}" (${linkedProjectId}) -> ${folderPath}`);
    } else {
      console.log("[setup] Project link response missing project id; kept local mapping only.");
    }
  } catch (err) {
    console.error("[setup] Backend link failed:", err.message);
    console.log("[setup] Local config saved anyway. Link will retry on next setup.");
  }

  const openCursor = await ask("\nOpen Cursor in this project folder? (y/n): ");
  if (openCursor.trim().toLowerCase() === "y") {
    try {
      execSync(`cursor "${folderPath}"`, { stdio: "inherit" });
      console.log("[setup] Cursor opened.");
    } catch {
      console.log("[setup] Could not open Cursor. Make sure it's in your PATH.");
    }
  }

  console.log("\n[setup] Done! Run `npm start` to begin receiving commands.\n");
  rl.close();
}
