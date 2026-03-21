import { spawn } from "node:child_process";

const MAX_CHUNK = 4000;

function chunkText(text, maxBytes = MAX_CHUNK) {
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

export function executeCommand(command, cwd) {
  return new Promise((resolve) => {
    let stdout = "";
    let stderr = "";

    const proc = spawn(command, {
      cwd,
      shell: true,
      stdio: ["ignore", "pipe", "pipe"],
    });

    proc.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    proc.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    proc.on("error", (err) => {
      stderr += `spawn error: ${err.message}\n`;
    });

    proc.on("close", (code) => {
      resolve({
        exitCode: code ?? 1,
        stdoutChunks: chunkText(stdout),
        stderrChunks: chunkText(stderr),
      });
    });
  });
}
