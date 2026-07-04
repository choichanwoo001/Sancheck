import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  AGENT_MAP_EVENT_VERSION,
  dispatchDwellEvent,
} from '../agent/runtime/agentEventBus'
import type { AgentContext } from '../agent/types'
import { DEMO_BOOKS } from '../data/demoScenario'
import type { PipelineItem } from './chatAgent/assistantOutputPipeline'
import { useFixtureShelfArrivalBrief } from './useFixtureShelfArrivalBrief'

function createContext(patch: Partial<AgentContext> = {}): AgentContext {
  return {
    state: 'NAV_EXEC',
    mobilityPaused: false,
    listType: 'shopping',
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
    ...patch,
  } as AgentContext
}

describe('useFixtureShelfArrivalBrief', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('shows the book arrival brief urgently and switches away from stale detour state', async () => {
    const contextRef = {
      current: createContext({
        actualTwoBookRouteActive: false,
        transitDetourPhase: 'await_reco_accept',
        pendingDwellBook: {
          booksId: DEMO_BOOKS.serendipity.fallbackBooksId,
          title: DEMO_BOOKS.serendipity.title,
          authors: DEMO_BOOKS.serendipity.authors,
          detectedAt: Date.now(),
          source: 'cover',
        },
        awaitingDwellFeedback: true,
        skippedDwellBook: {
          booksId: DEMO_BOOKS.serendipity.fallbackBooksId,
          title: DEMO_BOOKS.serendipity.title,
          authors: DEMO_BOOKS.serendipity.authors,
          detectedAt: Date.now(),
          source: 'cover',
        },
      }),
    }
    const enqueueAssistantMany = vi.fn(async (_items: PipelineItem[]) => undefined)
    const appendAssistant = vi.fn(async (_text: string) => undefined)
    const setContext = vi.fn((patch: Partial<AgentContext>) => {
      contextRef.current = { ...contextRef.current, ...patch }
    })

    const { unmount } = renderHook(() =>
      useFixtureShelfArrivalBrief({
        enqueueAssistantMany,
        appendAssistant,
        contextRef,
        setContext,
      }),
    )

    dispatchDwellEvent({
      type: 'SHELF_ARRIVED',
      version: AGENT_MAP_EVENT_VERSION,
      legIndex: 0,
      poolIndex: null,
      waypointId: 'book2',
      label: DEMO_BOOKS.book2.title,
    })

    await waitFor(() => {
      expect(appendAssistant).toHaveBeenCalledTimes(4)
    })
    expect(enqueueAssistantMany).not.toHaveBeenCalled()
    expect(appendAssistant.mock.calls[0]?.[0]).toContain(DEMO_BOOKS.book2.title)
    expect(appendAssistant.mock.calls[1]?.[0]).toBe(DEMO_BOOKS.book2.reviewBrief)
    expect(appendAssistant.mock.calls[2]?.[0]).toBe(DEMO_BOOKS.book2.authorBioBrief)
    expect(setContext).toHaveBeenCalledWith(
      expect.objectContaining({
        dwellDialogueActiveBookKey: 'book2',
        dwellDialogueStep: 'intro',
        mobilityPaused: true,
      }),
    )
    expect(contextRef.current).toEqual(
      expect.objectContaining({
        dwellDialogueActiveBookKey: 'book2',
        dwellDialogueStep: 'intro',
        transitDetourPhase: 'idle',
        pendingDwellBook: null,
        awaitingDwellFeedback: false,
        skippedDwellBook: null,
      }),
    )

    unmount()
  })

  it('shows the adulting book arrival brief and sets book1 feedback state', async () => {
    const contextRef = { current: createContext({ actualTwoBookRouteActive: true }) }
    const enqueueAssistantMany = vi.fn(async (_items: PipelineItem[]) => undefined)
    const appendAssistant = vi.fn(async (_text: string) => undefined)
    const setContext = vi.fn((patch: Partial<AgentContext>) => {
      contextRef.current = { ...contextRef.current, ...patch }
    })

    const { unmount } = renderHook(() =>
      useFixtureShelfArrivalBrief({
        enqueueAssistantMany,
        appendAssistant,
        contextRef,
        setContext,
      }),
    )

    dispatchDwellEvent({
      type: 'SHELF_ARRIVED',
      version: AGENT_MAP_EVENT_VERSION,
      legIndex: 1,
      poolIndex: null,
      waypointId: 'book1',
      label: DEMO_BOOKS.book1.title,
    })

    await waitFor(() => {
      expect(appendAssistant).toHaveBeenCalledTimes(4)
    })
    expect(enqueueAssistantMany).not.toHaveBeenCalled()
    expect(appendAssistant.mock.calls[0]?.[0]).toContain(DEMO_BOOKS.book1.title)
    expect(appendAssistant.mock.calls[1]?.[0]).toBe(DEMO_BOOKS.book1.reviewBrief)
    expect(appendAssistant.mock.calls[2]?.[0]).toBe(DEMO_BOOKS.book1.authorBioBrief)
    expect(appendAssistant.mock.calls[3]?.[0]).toBe('원하는 현실적인 부분이 있는 책인가요?')
    expect(contextRef.current).toEqual(
      expect.objectContaining({
        dwellDialogueActiveBookKey: 'book1',
        dwellDialogueStep: 'intro',
        mobilityPaused: true,
      }),
    )

    unmount()
  })

  it('allows repeated external waypoint arrivals when no app navigation run exists', async () => {
    const contextRef = { current: createContext() }
    const enqueueAssistantMany = vi.fn(async (_items: PipelineItem[]) => undefined)
    const appendAssistant = vi.fn(async (_text: string) => undefined)
    const setContext = vi.fn((patch: Partial<AgentContext>) => {
      contextRef.current = { ...contextRef.current, ...patch }
    })

    const { unmount } = renderHook(() =>
      useFixtureShelfArrivalBrief({
        enqueueAssistantMany,
        appendAssistant,
        contextRef,
        setContext,
      }),
    )

    const event = {
      type: 'SHELF_ARRIVED' as const,
      version: AGENT_MAP_EVENT_VERSION,
      legIndex: 0,
      poolIndex: null,
      waypointId: 'book2',
      label: DEMO_BOOKS.book2.title,
    }
    dispatchDwellEvent(event)
    dispatchDwellEvent(event)

    await waitFor(() => {
      expect(appendAssistant).toHaveBeenCalledTimes(8)
    })
    expect(enqueueAssistantMany).not.toHaveBeenCalled()

    unmount()
  })
})
