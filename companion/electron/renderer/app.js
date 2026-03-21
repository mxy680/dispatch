function $id(id) {
  return document.getElementById(id);
}

function basename(p) {
  const parts = String(p ?? "").split(/[/\\]+/).filter(Boolean);
  return parts.length ? parts[parts.length - 1] : "";
}

function setStatus(msg) {
  $id("status").textContent = msg ?? "";
}

async function init() {
  if (!window.dispatchCompanion) {
    setStatus("GUI preload missing: window.dispatchCompanion is undefined");
    return;
  }

  try {
    const info = await window.dispatchCompanion.getAppInfo();
    const v = info?.version ?? "?";
    const n = info?.name ?? "dispatch-companion";
    $id("appVersionLine").textContent = `Build: ${n} v${v} (Electron desktop companion)`;
  } catch {
    $id("appVersionLine").textContent = "Build: version unknown";
  }

  const cfg = await window.dispatchCompanion.getConfig();
  const paired = Boolean(cfg?.deviceToken && cfg?.deviceId);

  // Always show pairing + reset — a saved token can be stale (401) and users must re-pair.
  $id("pairCard").style.display = "block";
  if (cfg?.backendUrl) {
    $id("backendUrl").value = String(cfg.backendUrl);
  }

  $id("tokenCard").style.display = paired ? "block" : "none";
  $id("setupCard").style.display = paired ? "block" : "none";

  $id("deviceId").textContent = cfg?.deviceId ?? "-";
  $id("deviceToken").textContent = cfg?.deviceToken ?? "-";

  if (paired) {
    try {
      await refreshProjects();
    } catch (e) {
      const msg = String(e?.message ?? e);
      setStatus(
        `${msg}\n\nIf you see 401 / Invalid device token: click **Reset connection**, then create a new pairing code in the web app and pair again. Also confirm Backend URL matches your server.`
      );
    }
  }
}

async function refreshProjects() {
  const links = await window.dispatchCompanion.getLinkedProjects();
  const tbody = $id("projectsTbody");
  tbody.innerHTML = "";

  for (const link of links) {
    const tr = document.createElement("tr");
    const projectName = link.project_name || link.project_id || "-";
    const localPath = link.local_path || link.localPath || "";
    const missing = !localPath;

    tr.innerHTML = `
      <td>${escapeHtml(projectName)}</td>
      <td class="mono">${escapeHtml(localPath || "(not linked)")}</td>
      <td class="mono">
        <button data-choose="${escapeAttr(projectName)}">Choose Folder</button>
        <button data-open="${escapeAttr(localPath)}" ${missing ? "disabled" : ""}>Open Cursor</button>
      </td>
    `;
    tbody.appendChild(tr);
  }

  tbody.querySelectorAll("button[data-open]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const folderPath = btn.getAttribute("data-open");
      if (!folderPath) return;
      try {
        setStatus("Opening Cursor...");
        await window.dispatchCompanion.openCursor({ folderPath });
        setStatus("Cursor opened (if installed in PATH).");
      } catch (e) {
        setStatus(`Failed to open Cursor: ${String(e?.message ?? e)}`);
      }
    });
  });

  // Choose folder per project.
  tbody.querySelectorAll("button[data-choose]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const projectName = btn.getAttribute("data-choose");
      if (!projectName) return;

      try {
        setStatus(`Selecting folder for ${projectName}...`);
        const folderPath = await window.dispatchCompanion.selectProjectDirectory();
        if (!folderPath) {
          setStatus("Folder selection cancelled.");
          return;
        }

        // Persist mapping to backend so worker uses the right local_path.
        setStatus(`Linking ${projectName}...`);
        await window.dispatchCompanion.linkProject({ projectName, localPath: folderPath });
        setStatus("Linked. Refreshing projects...");
        await refreshProjects();
      } catch (e) {
        setStatus(`Link failed: ${String(e?.message ?? e)}`);
      }
    });
  });
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(s) {
  // Minimal: avoid breaking attribute values.
  return String(s ?? "").replaceAll('"', "&quot;");
}

function wireReset() {
  return async () => {
    try {
      setStatus("Resetting connection...");
      await window.dispatchCompanion.resetConnection();
      setStatus("Reset complete. Relaunching...");
    } catch (e) {
      setStatus(`Reset failed: ${String(e?.message ?? e)}`);
    }
  };
}

window.addEventListener("DOMContentLoaded", () => {
  init().catch((e) => setStatus(`Init failed: ${String(e?.message ?? e)}`));

  $id("pairBtn").addEventListener("click", async () => {
    try {
      if (!window.dispatchCompanion?.pairDevice) {
        throw new Error("GUI preload missing: window.dispatchCompanion.pairDevice is undefined");
      }
      const backendUrl = $id("backendUrl").value.trim();
      const pairingCode = $id("pairingCode").value.trim();
      if (!backendUrl) throw new Error("Backend URL is required");
      if (!pairingCode) throw new Error("Pairing code is required");

      setStatus("Pairing device...");
      await window.dispatchCompanion.pairDevice({ backendUrl, pairingCode });
      setStatus("Paired successfully. Loading projects...");

      await init();
    } catch (e) {
      setStatus(`Pair failed: ${String(e?.message ?? e)}`);
    }
  });

  $id("resetBtn").addEventListener("click", wireReset());
  $id("resetBtnHeader").addEventListener("click", wireReset());

  $id("copyTokenBtn").addEventListener("click", async () => {
    try {
      const token = $id("deviceToken").textContent ?? "";
      await navigator.clipboard.writeText(token);
      setStatus("Token copied to clipboard.");
    } catch (e) {
      setStatus(`Copy failed: ${String(e?.message ?? e)}`);
    }
  });

  // One-click-ish: link all currently unlinked projects.
  $id("autoLinkBtn").addEventListener("click", async () => {
    try {
      setStatus("Auto-linking missing projects...");
      const links = await window.dispatchCompanion.getLinkedProjects();
      const missing = links.filter((l) => !l.local_path && !l.localPath);

      if (missing.length === 0) {
        setStatus("All projects already linked.");
        return;
      }

      // Sequential folder picker to keep the UX simple.
      for (const link of missing) {
        const projectName = link.project_name || link.project_id;
        setStatus(`Select folder for ${projectName}...`);
        const folderPath = await window.dispatchCompanion.selectProjectDirectory();
        if (!folderPath) {
          setStatus("Auto-link cancelled.");
          return;
        }
        await window.dispatchCompanion.linkProject({ projectName, localPath: folderPath });
      }

      setStatus("Auto-link done. Refreshing...");
      await refreshProjects();
    } catch (e) {
      setStatus(`Auto-link failed: ${String(e?.message ?? e)}`);
    }
  });
});

