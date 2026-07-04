import { readLlmEnv } from '../agent/runtime/llmEnv'

export function isLlmConfigured(): boolean {
  return readLlmEnv() !== null
}
