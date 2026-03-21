import { getBackendUrl, getDeviceToken, getDeviceId } from "./config.js";

async function request(method, path, body = undefined) {
  const url = `${getBackendUrl()}${path}`;
  const headers = { "Content-Type": "application/json" };
  const token = getDeviceToken();
  if (token) headers["X-Device-Token"] = token;

  const res = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = json?.detail ?? res.statusText;
    throw new Error(`${method} ${path} ${res.status}: ${detail}`);
  }
  return json;
}

export async function completePairing(pairingCode, name, platform) {
  return request("POST", "/api/device/pair/complete", {
    pairing_code: pairingCode,
    name,
    platform,
  });
}

export async function heartbeat() {
  return request("POST", "/api/device/heartbeat", {
    device_id: getDeviceId(),
  });
}

export async function claimNext(waitSeconds = 20) {
  return request("POST", "/api/device/claim-next", {
    wait_seconds: waitSeconds,
  });
}

export async function appendLogs(commandId, sequenceStart, stream, chunks) {
  return request("POST", `/api/device/commands/${commandId}/append-logs`, {
    sequence_start: sequenceStart,
    stream,
    chunks,
  });
}

export async function completeCommand(commandId, status, exitCode) {
  return request("POST", `/api/device/commands/${commandId}/complete`, {
    status,
    exit_code: exitCode,
  });
}

export async function pushCursorContext(projectId, filePath, selection, diagnostics) {
  return request("POST", "/api/device/cursor-context", {
    project_id: projectId,
    file_path: filePath,
    selection,
    diagnostics,
  });
}

export async function getMyProjectLinks() {
  return request("GET", "/api/device/my-projects");
}

export async function linkProjectByName(projectName, localPath) {
  return request("POST", "/api/device/link-project", {
    project_name: projectName,
    local_path: localPath,
  });
}
