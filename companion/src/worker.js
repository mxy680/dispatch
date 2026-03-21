import { heartbeat, claimNext, appendLogs, completeCommand, getMyProjectLinks } from "./api.js";
import { getDeviceToken, loadConfig } from "./config.js";
import { executeCommand } from "./executor.js";

const HEARTBEAT_INTERVAL_MS = 10_000;
const CLAIM_WAIT_S = 20;
const MIN_BACKOFF_MS = 2_000;
const MAX_BACKOFF_MS = 30_000;
const PROJECT_REFRESH_MS = 60_000;
const DEFAULT_PROJECT_PATH = "/Users/alinawaf/Desktop/CSDS/CSDS393/dispatch/project"

function getCwd(job) {
  if (job.projectLocalPath && job.projectLocalPath.trim()) {
    return job.projectLocalPath;
  }
  return DEFAULT_PROJECT_PATH;
}

export function startWorker() {
  if (!getDeviceToken()) {
    console.log("[worker] no device token — pair first, then restart.");
    return;
  }

  const projectPathsByProjectId = {};
  let agentPath = null;

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
    loadLocalProjectPaths();
    try {
      const result = await getMyProjectLinks();
      for (const link of result?.links ?? []) {
        if (link.project_id && link.local_path) {
          projectPathsByProjectId[link.project_id] = link.local_path;
        }
      }
    } catch (err) {
      console.error("[worker] project-links refresh failed:", err.message);
    }
  }

  async function sendHeartbeat() {
    try {
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

      const commandId = cmd.id;
      const projectId = cmd.project_id;
      const cwd = cmd.project_local_path ?? projectPathsByProjectId[projectId] ?? process.cwd();
      const provider = String(cmd.provider ?? "shell").toLowerCase();
      const promptText = cmd.user_prompt ?? cmd.command ?? "";

      // Execute provider CLI based on terminal_commands metadata.
      // This links the llm intent parsing prompt -> companion execution.
      let commandText = cmd.command ?? "";
      if (provider === "cursor") {
        const agentBin = agentPath || "agent";
        commandText = `CI=1 NO_COLOR=1 TERM=dumb ${agentBin} -p ${shellQuote(
          promptText
        )} --output-format text`;
      } else if (provider === "claude") {
        commandText = `claude -p ${shellQuote(promptText)}`;
      } else if (provider === "shell") {
        commandText = String(cmd.command ?? "");
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
