import express from "express";
import { pushCursorContext } from "./api.js";

const BRIDGE_PORT = 43111;

export function startBridge() {
  const app = express();
  app.use(express.json());

  app.get("/health", (_req, res) => {
    res.json({ status: "ok", service: "dispatch-companion" });
  });

  app.post("/context", async (req, res) => {
    const { projectId, filePath, selection, diagnostics } = req.body ?? {};
    if (!projectId) {
      return res.status(400).json({ error: "projectId is required" });
    }
    try {
      const result = await pushCursorContext(projectId, filePath, selection, diagnostics);
      console.log(
        `[bridge] cursor context saved projectId=${projectId} ${result?.context_id ? `context_id=${result.context_id}` : ""}`
      );
      res.json({ success: true, ...result });
    } catch (err) {
      console.error("[bridge] context push failed:", err.message);
      res.status(502).json({ error: err.message });
    }
  });

  app.listen(BRIDGE_PORT, "127.0.0.1", () => {
    console.log(`[companion] localhost bridge listening on http://127.0.0.1:${BRIDGE_PORT}`);
  });
}
