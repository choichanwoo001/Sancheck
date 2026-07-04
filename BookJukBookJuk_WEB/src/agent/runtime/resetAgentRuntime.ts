import { resetStickyMapCommands } from './agentEventBus'

export const DEMO_DEBUG_STORAGE_KEY = 'bjbj:demo-debug-state'

const TRANSIENT_STORAGE_KEYS = [
  DEMO_DEBUG_STORAGE_KEY,
]

export function resetTransientAgentRuntimeState(): void {
  resetStickyMapCommands()

  try {
    for (const key of TRANSIENT_STORAGE_KEYS) {
      window.localStorage.removeItem(key)
    }
  } catch {
    // Storage can be unavailable in private windows or tests.
  }
}
