import { renderHook, act } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentContext } from '../agent/types'
import {
  dispatchPauseMobility,
  publishNavigationSync,
  resetStickyMapCommandsForTest,
  subscribeMapCommand,
  AGENT_MAP_EVENT_VERSION,
} from '../agent/runtime/agentEventBus'
import { useTransitSerendipityDetour } from './useTransitSerendipityDetour'

const SERENDIPITY_ARRIVAL_MESSAGE =
  '다시 산책을 재개하고 싶으면 오케이 제스처 주세요'

function makeContext(overrides: Partial<AgentContext> = {}): AgentContext {
  return {
    state: 'NAV_EXEC',
    mobilityPaused: false,
    listType: 'wishlist',
    shoppingList: [],
    cartItems: [],
    pendingDwellBook: null,
    awaitingDwellFeedback: false,
    skippedDwellBook: null,
    extendedRouteActive: false,
    transitDetourPhase: 'idle',
    actualStopRouteExtensionPending: false,
    actualTwoBookRouteActive: false,
    resumeLegAfterDetour: null,
    checkoutStatus: 'idle',
    receipt: null,
    kakaoPaySession: null,
    recentlyRecommendedBookIds: [],
    recommendationDiversityRound: 0,
    pendingConfirmation: null,
    lastToolResult: null,
    dwellDialogueActiveBookKey: null,
    dwellDialogueStep: null,
    ...overrides,
  }
}

function publishNavSync(overrides: Partial<Parameters<typeof publishNavigationSync>[0]> = {}) {
  publishNavigationSync({
    version: AGENT_MAP_EVENT_VERSION,
    navigationActive: true,
    mobilityPhase: 'walking',
    activeLeg: 0,
    distanceToGoalM: 5,
    highlightPathLengthM: 10,
    isAutoWalking: true,
    isManualWalking: false,
    isWalkMode: false,
    navigationSpawnReady: true,
    ttsSpeaking: false,
    mobilityHold: false,
    ...overrides,
  })
}

describe('useTransitSerendipityDetour', () => {
  beforeEach(() => {
    resetStickyMapCommandsForTest()
  })

  afterEach(() => {
    resetStickyMapCommandsForTest()
    vi.useRealTimers()
  })

  it('enters free_browse_scan on PAUSE_MOBILITY during leg0 transit', () => {
    const contextRef = { current: makeContext() }
    const setContext = vi.fn((patch: Partial<AgentContext>) => {
      contextRef.current = { ...contextRef.current, ...patch }
    })
    const appendAssistant = vi.fn(async () => {})
    const waitForTtsAndPipeline = vi.fn(async () => {})

    renderHook(() =>
      useTransitSerendipityDetour({ contextRef, setContext, appendAssistant, waitForTtsAndPipeline }),
    )

    publishNavSync()

    act(() => {
      dispatchPauseMobility()
    })

    expect(setContext).toHaveBeenCalledWith(
      expect.objectContaining({
        transitDetourPhase: 'free_browse_scan',
        resumeLegAfterDetour: 0,
      }),
    )
  })

  it('starts serendipity nav on follow_me when paused_for_follow', async () => {
    const contextRef = {
      current: makeContext({ transitDetourPhase: 'paused_for_follow' }),
    }
    const setContext = vi.fn((patch: Partial<AgentContext>) => {
      contextRef.current = { ...contextRef.current, ...patch }
    })
    const appendAssistant = vi.fn(async () => {})
    const waitForTtsAndPipeline = vi.fn(
      () => new Promise<void>(() => {}),
    )

    const goalsReceived: unknown[] = []
    const started: string[] = []
    const mapUnsub = subscribeMapCommand((command) => {
      if (command.type === 'SET_DIRECT_GOALS') goalsReceived.push(command.goals)
      if (command.type === 'START_NAVIGATION') started.push(command.type)
    })

    const { result } = renderHook(() =>
      useTransitSerendipityDetour({ contextRef, setContext, appendAssistant, waitForTtsAndPipeline }),
    )

    act(() => {
      const handled = result.current.handleFollowMeDetour()
      expect(handled).toBe(true)
    })

    expect(setContext).toHaveBeenCalledWith(
      expect.objectContaining({ transitDetourPhase: 'serendipity_nav', mobilityPaused: false }),
    )
    expect(result.current.browseCountdownActive).toBe(true)
    expect(goalsReceived.length).toBeGreaterThan(0)
    expect(started).toContain('START_NAVIGATION')
    expect(waitForTtsAndPipeline).not.toHaveBeenCalled()

    mapUnsub()
  })

  it('enters serendipity_arrived on completeSerendipityBrowse during serendipity_nav', () => {
    const contextRef = {
      current: makeContext({ transitDetourPhase: 'serendipity_nav' }),
    }
    const setContext = vi.fn((patch: Partial<AgentContext>) => {
      contextRef.current = { ...contextRef.current, ...patch }
    })
    const appendAssistant = vi.fn(async () => {})
    const waitForTtsAndPipeline = vi.fn(async () => {})
    const pauseListener = vi.fn()
    const mapUnsub = subscribeMapCommand((command) => {
      if (command.type === 'PAUSE_MOBILITY') pauseListener()
    })

    const { result } = renderHook(() =>
      useTransitSerendipityDetour({ contextRef, setContext, appendAssistant, waitForTtsAndPipeline }),
    )

    act(() => {
      const handled = result.current.completeSerendipityBrowse({
        title: '단 한 사람',
        author: '최진영',
      })
      expect(handled).toBe(true)
    })

    expect(setContext).toHaveBeenCalledWith(
      expect.objectContaining({
        transitDetourPhase: 'serendipity_arrived',
        mobilityPaused: true,
        pendingDwellBook: expect.objectContaining({ title: '단 한 사람' }),
      }),
    )
    expect(appendAssistant).toHaveBeenCalledWith(SERENDIPITY_ARRIVAL_MESSAGE)
    expect(appendAssistant.mock.invocationCallOrder[0]).toBeLessThan(
      pauseListener.mock.invocationCallOrder[0],
    )
    expect(result.current.browseCountdownActive).toBe(false)

    mapUnsub()
  })
})
