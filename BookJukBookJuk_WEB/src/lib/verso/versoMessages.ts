import type { VersoEvent, VersoPath, VersoStatus } from './types'

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function parseJsonPayload(payload: string): unknown | null {
  try {
    return JSON.parse(payload) as unknown
  } catch {
    return null
  }
}

function readString(record: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = record[key]
    if (typeof value === 'string' && value.trim()) return value
  }
  return undefined
}

function readNestedRecord(record: Record<string, unknown>, key: string): Record<string, unknown> | null {
  const value = record[key]
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

export function parseVersoStatusPayload(payload: string): VersoStatus | null {
  const data = parseJsonPayload(payload)
  if (!data || typeof data !== 'object') return null
  const record = data as Record<string, unknown>
  if (record.type !== 'status') return null
  const position = record.position
  if (!position || typeof position !== 'object') return null
  const pos = position as Record<string, unknown>
  if (!isFiniteNumber(pos.x) || !isFiniteNumber(pos.y) || !isFiniteNumber(pos.heading)) return null
  if (typeof record.mode !== 'string') return null
  if (typeof record.is_moving !== 'boolean') return null
  if (!isFiniteNumber(record.remaining_waypoints)) return null

  const waypointId = record.current_waypoint_id
  const currentWaypointId =
    waypointId === null || waypointId === undefined
      ? null
      : typeof waypointId === 'string'
        ? waypointId
        : null

  return {
    x: pos.x,
    y: pos.y,
    heading: pos.heading,
    mode: record.mode,
    isMoving: record.is_moving,
    currentWaypointId,
    remainingWaypoints: record.remaining_waypoints,
  }
}

export function parseVersoPathPayload(payload: string): VersoPath | null {
  const data = parseJsonPayload(payload)
  if (!data || typeof data !== 'object') return null
  const record = data as Record<string, unknown>
  if (record.type !== 'path') return null
  if (!Array.isArray(record.poses)) return null

  const poses: VersoPath['poses'] = []
  for (const pose of record.poses) {
    if (!pose || typeof pose !== 'object') return null
    const p = pose as Record<string, unknown>
    if (!isFiniteNumber(p.x) || !isFiniteNumber(p.y)) return null
    poses.push({ x: p.x, y: p.y })
  }

  return { poses }
}

export function parseVersoEventPayload(payload: string): VersoEvent | null {
  const data = parseJsonPayload(payload)
  if (!data || typeof data !== 'object') return null
  const record = data as Record<string, unknown>
  if (record.type !== 'event') return null
  const rawEvent = readString(record, ['event', 'name', 'type'])
  if (!rawEvent || rawEvent === 'event') return null

  const waypoint = readNestedRecord(record, 'waypoint')
  const eventName =
    rawEvent === 'arrived' || rawEvent === 'waypoint_reached' || rawEvent === 'goal_reached'
      ? 'waypoint_arrived'
      : rawEvent
  const waypointId =
    readString(record, ['waypoint_id', 'waypointId', 'wp_id', 'wpId', 'id', 'book_id', 'bookId']) ??
    (waypoint ? readString(waypoint, ['id', 'waypoint_id', 'waypointId']) : undefined)
  const label =
    readString(record, ['label', 'waypoint_label', 'waypointLabel', 'title']) ??
    (waypoint ? readString(waypoint, ['label', 'title', 'name']) : undefined)

  const event: VersoEvent = { event: eventName }
  if (waypointId) event.waypointId = waypointId
  if (label) event.label = label
  return event
}

export const VERSO_TOPICS = {
  status: '/verso/status',
  path: '/verso/path',
  event: '/verso/event',
  command: '/verso/command',
  waypoints: '/verso/waypoints',
} as const
