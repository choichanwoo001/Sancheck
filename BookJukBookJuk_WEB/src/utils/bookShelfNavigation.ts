export function clampPoolIndices(indices: number[], poolSize: number): number[] {
  if (poolSize <= 0) return []
  return indices.map((idx) => Math.max(0, Math.min(poolSize - 1, idx)))
}

export function resolveMissionPoolIndices(
  requested: number[],
  poolSize: number,
  fallbackVersion: number,
): number[] {
  const clamped = clampPoolIndices(requested, poolSize)
  void fallbackVersion
  return clamped
}
