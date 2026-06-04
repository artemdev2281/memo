import { invoke } from "@tauri-apps/api/core";

let _port: number | null = null;

export async function getBackendPort(): Promise<number> {
  if (_port !== null) return _port;

  for (let attempt = 0; attempt < 40; attempt++) {
    const port = await invoke<number | null>("get_backend_port");
    if (port !== null) {
      _port = port;
      return port;
    }
    await new Promise((r) => setTimeout(r, 250));
  }

  throw new Error("Backend did not start within 10 seconds");
}
