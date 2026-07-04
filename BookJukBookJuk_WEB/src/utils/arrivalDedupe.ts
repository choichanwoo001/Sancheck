export type ArrivalDedupeEvent =
  | {
      type: 'SHELF_ARRIVED'
      legIndex: number
      poolIndex: number | null
      waypointId?: string
      label?: string
    }
  | { type: 'CHECKOUT_ARRIVED' }

export function buildArrivalDedupeKey(
  navigationRunId: number,
  event: ArrivalDedupeEvent,
): string {
  if (event.type === 'CHECKOUT_ARRIVED') return `${navigationRunId}:checkout`
  if (event.waypointId) return `${navigationRunId}:shelf:wp:${event.waypointId}`
  if (event.label) return `${navigationRunId}:shelf:label:${event.label}`
  return `${navigationRunId}:shelf:${event.legIndex}:${event.poolIndex ?? 'none'}`
}

export function claimArrivalEvent(
  processedKeys: Set<string>,
  navigationRunId: number,
  event: ArrivalDedupeEvent,
): boolean {
  const key = buildArrivalDedupeKey(navigationRunId, event)
  if (processedKeys.has(key)) return false
  processedKeys.add(key)
  return true
}
