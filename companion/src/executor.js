import { spawn } from "node:child_process";

const MAX_CHUNK = 4000;

export function chunkText(text, maxBytes = MAX_CHUNK) {
  if (!text) return [];
  const chunks = [];
  let buf = "";
  for (const ch of text) {
    buf += ch;
    if (Buffer.byteLength(buf) >= maxBytes) {
      chunks.push(buf);
      buf = "";
    }
  }
  if (buf) chunks.push(buf);
  return chunks;
}

/**
 * Execute a command, streaming output via onData callback.
 *
 * @param {string} command - Shell command to run
 * @param {string} cwd - Working directory
 * @param {(stream: "stdout"|"stderr", chunks: string[]) => void} [onData] - Called with chunks as they arrive
 * @returns {Promise<{exitCode: number}>}
 */
export function executeCommand(command, cwd, onData) {
  return new Promise((resolve) => {
    const proc = spawn(command, {
      cwd,
      shell: true,
      stdio: ["ignore", "pipe", "pipe"],
    });

    proc.stdout.on("data", (data) => {
      if (onData) {
        const chunks = chunkText(data.toString());
        if (chunks.length > 0) onData("stdout", chunks);
      }
    });

    proc.stderr.on("data", (data) => {
      if (onData) {
        const chunks = chunkText(data.toString());
        if (chunks.length > 0) onData("stderr", chunks);
      }
    });

    proc.on("error", (err) => {
      if (onData) onData("stderr", [`spawn error: ${err.message}\n`]);
    });

    proc.on("close", (code) => {
      resolve({ exitCode: code ?? 1 });
    });
  });
}
