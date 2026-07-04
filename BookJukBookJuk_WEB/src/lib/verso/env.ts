export const VERSO_ROSBRIDGE_URL_STORAGE_KEY = 'bjbj:verso-rosbridge-url'
export const DEFAULT_FAKE_ROSBRIDGE_URL = 'ws://127.0.0.1:9090'

export function readVersoRosbridgeDefaultUrl(): string {
  return import.meta.env.VITE_VERSO_ROSBRIDGE_URL?.trim() || DEFAULT_FAKE_ROSBRIDGE_URL
}

/** Last saved URL or env default. Demo and real flows both connect through rosbridge. */
export function readStoredVersoRosbridgeUrl(): string {
  try {
    const stored = localStorage.getItem(VERSO_ROSBRIDGE_URL_STORAGE_KEY)?.trim() ?? ''
    if (stored) return stored
  } catch {
    // ignore
  }
  return readVersoRosbridgeDefaultUrl()
}

export function writeStoredVersoRosbridgeUrl(url: string): void {
  try {
    const trimmed = url.trim()
    if (trimmed) {
      localStorage.setItem(VERSO_ROSBRIDGE_URL_STORAGE_KEY, trimmed)
    } else {
      localStorage.removeItem(VERSO_ROSBRIDGE_URL_STORAGE_KEY)
    }
  } catch {
    // ignore
  }
}
