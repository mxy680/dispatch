import { pairDevice } from "./pair.js";
import { runSetup } from "./setup.js";
import { startBridge } from "./bridge.js";
import { startWorker } from "./worker.js";
import { getDeviceToken, loadConfig } from "./config.js";

const args = process.argv.slice(2);

async function main() {
  if (args[0] === "pair") {
    const backendUrl = args[1];
    const pairingCode = args[2];
    if (!backendUrl || !pairingCode) {
      console.error("Usage: node src/index.js pair <backend-url> <pairing-code>");
      process.exit(1);
    }
    await pairDevice(backendUrl, pairingCode);
    console.log("\nPairing complete. Run `node src/index.js setup` to link projects.\n");
    return;
  }

  if (args[0] === "setup") {
    await runSetup();
    return;
  }

  if (!getDeviceToken()) {
    console.error(
      "[companion] Not paired yet.\n" +
        "  1) In the web app, go to Settings -> Create pairing code.\n" +
        "  2) Run: node src/index.js pair http://localhost:8000 <pairing-code>\n" +
        "  3) Run: node src/index.js setup\n" +
        "  4) Then run: npm start"
    );
    process.exit(1);
  }

  const config = loadConfig();
  console.log(`[companion] starting device_id=${config.deviceId} backend=${config.backendUrl}`);

  startBridge();
  startWorker();
}

main().catch((err) => {
  console.error("[companion] fatal:", err);
  process.exit(1);
});
