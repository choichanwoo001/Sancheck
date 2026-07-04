import { describe, expect, it } from 'vitest'
import { DEMO_BOOKS } from '../../data/demoScenario'
import { mapImageOffsetX, mapImageOffsetZ } from '../../data/mapData'
import {
  initialRobotMissionWaypoints,
  ROBOT_MAP_BOOK1,
  ROBOT_MAP_BOOK2,
  ROBOT_MAP_START,
  ROBOT_MAP_START_ORIENTATION,
  robotMapBook1WorldXz,
  robotMapBook2WorldXz,
  robotMapStartWorldXz,
} from './robotMissionCoords'

describe('robotMissionCoords', () => {
  it('defines robot map frame start and book2 coordinates', () => {
    expect(ROBOT_MAP_START).toEqual({ x: -21.987, y: 6.568 })
    expect(ROBOT_MAP_START_ORIENTATION).toEqual({ z: 0.562, w: 0.827 })
    expect(ROBOT_MAP_BOOK2).toEqual({ x: -25.504, y: -13.313 })
    expect(ROBOT_MAP_BOOK1).toEqual({ x: -47.645, y: -4.270 })
  })

  it('converts robot map coords to web world xz', () => {
    expect(robotMapStartWorldXz()).toEqual([
      ROBOT_MAP_START.x - mapImageOffsetX,
      ROBOT_MAP_START.y - mapImageOffsetZ,
    ])
    expect(robotMapBook2WorldXz()).toEqual([
      ROBOT_MAP_BOOK2.x - mapImageOffsetX,
      ROBOT_MAP_BOOK2.y - mapImageOffsetZ,
    ])
    expect(robotMapBook1WorldXz()).toEqual([
      ROBOT_MAP_BOOK1.x - mapImageOffsetX,
      ROBOT_MAP_BOOK1.y - mapImageOffsetZ,
    ])
  })

  it('builds initial mission waypoints for 오직 두 사람 only', () => {
    const waypoints = initialRobotMissionWaypoints()
    expect(waypoints).toEqual([{
      id: 'book2',
      x: ROBOT_MAP_BOOK2.x,
      y: ROBOT_MAP_BOOK2.y,
      label: DEMO_BOOKS.book2.title,
    }])
  })
})
