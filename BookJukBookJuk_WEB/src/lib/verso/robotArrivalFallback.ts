import { DEMO_BOOKS, findDemoBookByTitle, type DemoBookKey } from '../../data/demoScenario'
import { ROBOT_MAP_BOOK1, ROBOT_MAP_BOOK2 } from './robotMissionCoords'
import type { VersoEvent } from './types'

export type RobotArrivalTarget = {
  mapping: number | 'checkout'
  waypointId?: string
  label?: string
  robotX?: number
  robotY?: number
}

const DEMO_WAYPOINT_LEG: Partial<Record<DemoBookKey, number>> = {
  book2: 0,
  book1: 1,
  serendipity: 0,
}

const DEMO_WAYPOINT_COORDS: Partial<Record<DemoBookKey, { x: number; y: number }>> = {
  book2: ROBOT_MAP_BOOK2,
  book1: ROBOT_MAP_BOOK1,
}

function isDemoBookKey(value: string): value is DemoBookKey {
  return Object.prototype.hasOwnProperty.call(DEMO_BOOKS, value)
}

export function resolveRobotArrivalFallback(
  event: Pick<VersoEvent, 'waypointId' | 'label'>,
): RobotArrivalTarget | null {
  if (event.waypointId === 'checkout') {
    return {
      mapping: 'checkout',
      waypointId: event.waypointId,
      label: event.label,
    }
  }

  const key =
    event.waypointId && isDemoBookKey(event.waypointId)
      ? event.waypointId
      : event.label
        ? findDemoBookByTitle(event.label)?.key
        : null

  if (!key) return null

  const leg = DEMO_WAYPOINT_LEG[key]
  if (leg == null) return null

  return {
    mapping: leg,
    waypointId: event.waypointId ?? key,
    label: event.label ?? DEMO_BOOKS[key].title,
    robotX: DEMO_WAYPOINT_COORDS[key]?.x,
    robotY: DEMO_WAYPOINT_COORDS[key]?.y,
  }
}
