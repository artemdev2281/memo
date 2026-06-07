import { invoke } from "@tauri-apps/api/core";

let _port: number | null = null;
let _inFlight: Promise<number> | null = null;

async function poll(): Promise<number> {
  for (let attempt = 0; attempt < 120; attempt++) {
    const port = await invoke<number | null>("get_backend_port");
    if (port !== null) {
      _port = port;
      return port;
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error("Backend did not start within 30 seconds");
}

export async function getBackendPort(): Promise<number> {
  if (_port !== null) return _port;
  // Dedupe concurrent callers onto one poll loop; reset on failure so a later
  // call can retry (e.g. if the backend restarts mid-session).
  if (_inFlight === null) {
    _inFlight = poll().finally(() => { _inFlight = null; });
  }
  return _inFlight;
}
