import { describe, expect, it } from 'vitest'
import { DEMO_BOOKS } from '../../data/demoScenario'
import { resolveRobotArrivalFallback } from './robotArrivalFallback'

describe('resolveRobotArrivalFallback', () => {
  it('maps demo waypoint ids when the app did not publish the mission itself', () => {
    expect(resolveRobotArrivalFallback({ waypointId: 'book2' })).toMatchObject({
      mapping: 0,
      waypointId: 'book2',
      label: DEMO_BOOKS.book2.title,
    })
    expect(resolveRobotArrivalFallback({ waypointId: 'book1' })).toMatchObject({
      mapping: 1,
      waypointId: 'book1',
      label: DEMO_BOOKS.book1.title,
    })
  })

  it('can infer the demo waypoint from a label', () => {
    expect(resolveRobotArrivalFallback({ label: DEMO_BOOKS.book2.title })).toMatchObject({
      mapping: 0,
      waypointId: 'book2',
    })
    expect(resolveRobotArrivalFallback({ label: DEMO_BOOKS.book1.title })).toMatchObject({
      mapping: 1,
      waypointId: 'book1',
    })
  })

  it('keeps checkout arrivals routable', () => {
    expect(resolveRobotArrivalFallback({ waypointId: 'checkout' })).toEqual({
      mapping: 'checkout',
      waypointId: 'checkout',
      label: undefined,
    })
  })

  it('ignores unknown waypoints', () => {
    expect(resolveRobotArrivalFallback({ waypointId: 'unknown' })).toBeNull()
  })
})
