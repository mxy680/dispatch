import { heartbeat, claimNext, appendLogs, completeCommand, getMyProjectLinks } from "./api.js";
import { getDeviceToken, loadConfig } from "./config.js";
import { executeCommand } from "./executor.js";
import fs from "node:fs";
import { execSync } from "node:child_process";
import { saveConfig } from "./config.js";
import path from "node:path";
import os from "node:os";

const HEARTBEAT_INTERVAL_MS = 10_000;
const CLAIM_WAIT_S = 20;
const MIN_BACKOFF_MS = 2_000;
const MAX_BACKOFF_MS = 30_000;
const PROJECT_REFRESH_MS = 60_000;

export function startWorker() {
  if (!getDeviceToken()) {
    console.log("[worker] no device token — pair first, then restart.");
    return false;
  }

  const projectPathsByProjectId = {};
  let agentPath = null;
  const sessionCwds = {}; // per terminal session cwd (so `cd` persists)
  const trustedWorkspaces = new Set(loadConfig().trustedWorkspaces ?? []);

  function markWorkspaceTrusted(workspacePath) {
    if (!workspacePath) return;
    trustedWorkspaces.add(workspacePath);
    try {
      saveConfig({ trustedWorkspaces: Array.from(trustedWorkspaces) });
    } catch (e) {
      console.error("[worker] failed to persist trustedWorkspaces:", String(e?.message ?? e));
    }
  }

  function parseCdCommand(commandText) {
    const trimmed = String(commandText ?? "").trim();
    // Only handle a simple `cd <path>` (no &&, ;, etc).
    const match = trimmed.match(/^cd\s+(.+?)\s*$/);
    if (!match) return null;
    const targetRaw = match[1].trim();
    if (!targetRaw || /[;&|]/.test(targetRaw)) return null;
    // Strip surrounding quotes if present.
    const target = targetRaw.replace(/^['"]|['"]$/g, "");
    return target || null;
  }

  function resolveCdTarget(target, baseCwd) {
    let resolved = target;
    if (resolved.startsWith("~/")) resolved = path.join(os.homedir(), resolved.slice(2));
    else if (resolved === "~") resolved = os.homedir();
    if (!path.isAbsolute(resolved)) resolved = path.resolve(baseCwd, resolved);
    return resolved;
  }

  function detectAgentPath() {
    const candidates = ["agent", "cursor-agent"];
    for (const c of candidates) {
      try {
        const resolved = execSync(`command -v ${c} 2>/dev/null || which ${c} 2>/dev/null`, {
          stdio: "pipe",
          timeout: 5000,
        })
          .toString()
          .trim();
        if (resolved) return resolved;
      } catch {
        continue;
      }
    }

    // Electron apps often don't inherit PATH, so we also look in Cursor's bundled
    // agent runtime location.
    try {
      const base = path.join(os.homedir(), ".local", "share", "cursor-agent", "versions");
      if (fs.existsSync(base) && fs.statSync(base).isDirectory()) {
        // Pick the newest *version that contains a runnable agent binary*.
        // Cursor installs multiple runtime folders; the binary may not be in the newest one.
        const entries = fs
          .readdirSync(base, { withFileTypes: true })
          .filter((e) => e.isDirectory())
          .map((e) => {
            const full = path.join(base, e.name);
            const mtimeMs = fs.statSync(full).mtimeMs;
            return { name: e.name, mtimeMs };
          })
          .sort((a, b) => b.mtimeMs - a.mtimeMs);

        for (const v of entries) {
          const candidate = path.join(base, v.name, "cursor-agent");
          if (fs.existsSync(candidate)) return candidate;
          const legacy = path.join(base, v.name, "agent");
          if (fs.existsSync(legacy)) return legacy;
        }
      }
    } catch {
      // ignore
    }

    return null;
  }

  function resolveAgentPathFromConfig() {
    const cfg = loadConfig();
    agentPath = typeof cfg.agentPath === "string" && cfg.agentPath.length > 0 ? cfg.agentPath : null;
  }

  function rewriteCommandForAgentPath(commandText) {
    if (!commandText.startsWith("agent ")) return commandText;
    if (!agentPath) return commandText;
    return `${agentPath}${commandText.slice("agent".length)}`;
  }

  function loadLocalProjectPaths() {
    const config = loadConfig();
    const local = config.localProjects ?? {};
    for (const [, entry] of Object.entries(local)) {
      if (entry.projectId && entry.path) {
        projectPathsByProjectId[entry.projectId] = entry.path;
      }
    }
  }

  async function refreshProjectLinks() {
    resolveAgentPathFromConfig();
    if (!agentPath) {
      const detected = detectAgentPath();
      if (detected) {
        agentPath = detected;
        try {
          saveConfig({ agentPath: detected });
          console.log(`[worker] detected Cursor agent binary: ${detected}`);
        } catch (e) {
          console.error("[worker] failed to persist detected agentPath:", String(e?.message ?? e));
        }
      }
    }
    loadLocalProjectPaths();
    try {
      const result = await getMyProjectLinks();
      for (const link of result?.links ?? []) {
        if (link.project_id && link.local_path) {
          projectPathsByProjectId[link.project_id] = link.local_path;
          // Proactively create the folder so first command has a working cwd.
          try {
            if (typeof link.local_path === "string" && link.local_path.trim()) {
              const p = String(link.local_path);
              if (path.isAbsolute(p) && p !== "/" && !fs.existsSync(p)) {
                fs.mkdirSync(p, { recursive: true });
                console.log(`[worker] created linked project directory ${p}`);
              }
            }
          } catch {
            // ignore; we'll still rely on execution-time checks
          }
        }
      }
    } catch (err) {
      console.error("[worker] project-links refresh failed:", err.message);
    }
  }

  async function sendHeartbeat() {
    try {
      const token = getDeviceToken();
      const deviceId = loadConfig().deviceId;
      console.log(`[worker] heartbeat auth token=${token ? "present" : "missing"} deviceId=${deviceId ?? "-"}`);
      await heartbeat();
    } catch (err) {
      console.error("[worker] heartbeat failed:", err.message);
    }
  }

  refreshProjectLinks();
  setInterval(refreshProjectLinks, PROJECT_REFRESH_MS);
  sendHeartbeat();
  setInterval(sendHeartbeat, HEARTBEAT_INTERVAL_MS);

  async function loop() {
    let backoff = MIN_BACKOFF_MS;

    while (true) {
      let cmd = null;
      try {
        const result = await claimNext(CLAIM_WAIT_S);
        cmd = result?.command ?? null;
        backoff = MIN_BACKOFF_MS;
      } catch (err) {
        console.error("[worker] claim-next failed:", err.message);
        await sleep(backoff);
        backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
        continue;
      }

      if (!cmd) {
        await sleep(MIN_BACKOFF_MS);
        continue;
      }

      if (cmd.status && cmd.status !== "queued") {
        console.warn(
          `[worker] safety: received non-executable command id=${cmd.id} status=${cmd.status}; skipping`
        );
        await sleep(MIN_BACKOFF_MS);
        continue;
      }

      const commandId = cmd.id;
      const projectId = cmd.project_id;
      const sessionId = cmd.session_id;
      const resolvedFromDb = Boolean(cmd.project_local_path);
      const resolvedFromConfig = Boolean(projectPathsByProjectId[projectId]);
      const baseCwd = cmd.project_local_path ?? projectPathsByProjectId[projectId] ?? process.cwd();
      const cwd = sessionId && sessionCwds[sessionId] ? sessionCwds[sessionId] : baseCwd;
      const provider = String(cmd.provider ?? "shell").toLowerCase();
      const promptText = cmd.user_prompt ?? cmd.command ?? "";

      // Safety: never silently run in the companion directory.
      // If the device didn't link a local project folder (device_project_links.local_path),
      // executing commands in `process.cwd()` will write artifacts into the companion folder.
      if (!resolvedFromDb && !resolvedFromConfig) {
        const msg = `[config] Missing local_path for project_id=${projectId}. ` +
          `Run companion "Setup" and link a local project folder for this project.`;
        console.error(`[worker] ${msg}`);
        try {
          await appendLogs(commandId, 0, "stderr", [msg + "\n"]);
        } catch {
          // ignore append failures; we'll still mark command complete below
        }
        try {
          await completeCommand(commandId, "failed", 1);
        } catch (err) {
          console.error("[worker] complete failed:", err.message);
        }
        continue;
      }

      // If local path exists but is invalid, fail fast with a helpful error.
      if (typeof cwd === "string" && !fs.existsSync(cwd)) {
        // Create the directory on the user's machine so `cd`/commands work
        // on first-time setups where folders don't exist yet.
        try {
          fs.mkdirSync(cwd, { recursive: true });
          console.log(`[worker] created missing project directory cwd=${cwd}`);
        } catch (err) {
          const msg = `[config] local project path does not exist and failed to create: ${cwd}`;
          console.error(`[worker] ${msg}`);
          try {
            await appendLogs(commandId, 0, "stderr", [msg + "\n"]);
          } catch {
            // ignore append failures
          }
          try {
            await completeCommand(commandId, "failed", 1);
          } catch (err2) {
            console.error("[worker] complete failed:", err2.message);
          }
          continue;
        }
      }

      if (typeof cwd === "string") {
        const stat = fs.statSync(cwd);
        if (!stat.isDirectory()) {
          const msg = `[config] local project path is not a directory: ${cwd}`;
          console.error(`[worker] ${msg}`);
          try {
            await appendLogs(commandId, 0, "stderr", [msg + "\n"]);
          } catch {
            // ignore append failures
          }
          try {
            await completeCommand(commandId, "failed", 1);
          } catch (err) {
            console.error("[worker] complete failed:", err.message);
          }
          continue;
        }
      }

      // Execute provider CLI based on terminal_commands metadata.
      // This links the llm intent parsing prompt -> companion execution.
      let commandText = cmd.command ?? "";
      let workspaceToTrust = null;
      if (provider === "cursor") {
        const agentBin = agentPath;
        if (!agentBin) {
          const msg =
            "[config] Cursor provider selected but no Cursor 'agent' binary was found. " +
            "Make sure Cursor is installed and that either `agent` or `cursor-agent` is available in PATH. " +
            "You can also run the legacy companion setup once to save agentPath.";
          console.error(`[worker] ${msg}`);
          try {
            await appendLogs(commandId, 0, "stderr", [msg + "\n"]);
          } catch {
            // ignore
          }
          try {
            await completeCommand(commandId, "failed", 1);
          } catch (err) {
            console.error("[worker] complete failed:", err.message);
          }
          continue;
        }
        // Trust a workspace only the first time we execute in that directory.
        if (!trustedWorkspaces.has(cwd)) workspaceToTrust = cwd;
        const trustArgs = workspaceToTrust ? "--trust" : "";
        // --trust only works in headless print mode, so we always include --print.
        commandText = `CI=1 NO_COLOR=1 TERM=dumb ${agentBin} ${trustArgs} --workspace ${shellQuote(
          cwd
        )} -p ${shellQuote(promptText)} --print --output-format text`;
      } else if (provider === "claude") {
        commandText = `claude -p ${shellQuote(promptText)}`;
      } else if (provider === "shell") {
        commandText = String(cmd.command ?? "");

        // Persist `cd` across subsequent shell commands in the same session.
        const cdTarget = parseCdCommand(commandText);
        if (cdTarget) {
          const baseForCd = sessionId && sessionCwds[sessionId] ? sessionCwds[sessionId] : baseCwd;
          const nextCwd = resolveCdTarget(cdTarget, baseForCd);
          if (!fs.existsSync(nextCwd) || !fs.statSync(nextCwd).isDirectory()) {
            const msg = `cd: no such directory: ${nextCwd}`;
            console.error(`[worker] ${msg}`);
            try {
              await appendLogs(commandId, 0, "stderr", [msg + "\n"]);
            } catch {
              // ignore
            }
            try {
              await completeCommand(commandId, "failed", 1);
            } catch (err) {
              console.error("[worker] complete failed:", err.message);
            }
            continue;
          }

          if (sessionId) sessionCwds[sessionId] = nextCwd;
          console.log(`[worker] cd session_id=${sessionId} -> ${nextCwd}`);
          try {
            await completeCommand(commandId, "completed", 0);
          } catch (err) {
            console.error("[worker] complete failed:", err.message);
          }
          continue;
        }
      }

      // Backward compatibility: if backend still stores a literal "agent ..." command
      // and we have an absolute agentPath, rewrite the binary location.
      commandText = rewriteCommandForAgentPath(commandText);

      console.log(`[worker] executing command_id=${commandId} cwd=${cwd} cmd=${JSON.stringify(commandText)}`);

      const { exitCode, stdoutChunks, stderrChunks } = await executeCommand(commandText, cwd);

      let seq = 0;
      try {
        if (stdoutChunks.length > 0) {
          await appendLogs(commandId, seq, "stdout", stdoutChunks);
          seq += stdoutChunks.length;
        }
        if (stderrChunks.length > 0) {
          await appendLogs(commandId, seq, "stderr", stderrChunks);
          seq += stderrChunks.length;
        }
      } catch (err) {
        console.error("[worker] append-logs failed:", err.message);
      }

      const status = exitCode === 0 ? "completed" : "failed";
      if (stderrChunks.length > 0) {
        const stderrPreview = stderrChunks.join("").slice(0, 300).replace(/\n/g, "\\n");
        console.log(`[worker] stderr preview command_id=${commandId} ${stderrPreview}`);
      }
      try {
        if (provider === "cursor" && workspaceToTrust && status === "completed") {
          markWorkspaceTrusted(workspaceToTrust);
        }
        await completeCommand(commandId, status, exitCode);
      } catch (err) {
        console.error("[worker] complete failed:", err.message);
      }

      console.log(`[worker] done command_id=${commandId} status=${status} exit_code=${exitCode}`);
    }
  }

  loop().catch((err) => {
    console.error("[worker] fatal:", err);
  });

  return true;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function shellQuote(s) {
  // Safe single-quote wrapper for /bin/sh -c style commands.
  // Example: abc'd -> 'abc'\''d'
  const str = String(s ?? "");
  return `'${str.replace(/'/g, `'\\''`)}'`;
}
