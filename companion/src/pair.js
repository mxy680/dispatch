import { completePairing } from "./api.js";
import { saveConfig } from "./config.js";
import os from "node:os";

export async function pairDevice(backendUrl, pairingCode) {
  saveConfig({ backendUrl });

  const name = `Companion-${os.hostname()}`;
  const platform = os.platform();

  console.log(`[pair] pairing with code="${pairingCode}" backend=${backendUrl}`);

  const result = await completePairing(pairingCode, name, platform);
  if (!result?.device_token || !result?.device_id) {
    throw new Error("Pairing failed — invalid response from server");
  }

  saveConfig({
    backendUrl,
    deviceId: result.device_id,
    deviceToken: result.device_token,
    userId: result.user_id,
  });

  console.log(`[pair] success! device_id=${result.device_id}`);
  console.log(`[pair] config saved to ~/.dispatch-companion/config.json`);
  return result;
}
