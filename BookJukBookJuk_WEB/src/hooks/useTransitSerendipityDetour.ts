import { useCallback, useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'
import {
  dispatchPauseMobility,
  dispatchSetDirectGoals,
  dispatchStartNavigation,
  subscribeMapCommand,
  subscribeNavigationSync,
  type AgentMapSnapshot,
  type NavigationSyncState,
} from '../agent/runtime/agentEventBus'
import type { Point2 } from '../data/floorPlan'
import { serendipityOnlyDirectGoals } from '../data/fixtureRobotRoute'
import type { AgentContext } from '../agent/types'
import { DEMO_BOOKS, DEMO_DWELL_BOOK } from '../data/demoScenario'
import { recordUiMissionMessage } from '../lib/verso/rosbridgeUiLogStore'

const SERENDIPITY_ARRIVAL_MESSAGE =
  '다시 산책을 재개하고 싶으면 오케이 제스처 주세요'

export type SerendipityBrowseBook = {
  title: string
  author?: string
}

export type TransitSerendipityDetourDeps = {
  contextRef: RefObject<AgentContext>
  setContext: (patch: Partial<AgentContext>) => void
  appendAssistant: (text: string) => Promise<void>
  waitForTtsAndPipeline: () => Promise<void>
}

export function useTransitSerendipityDetour({
  contextRef,
  setContext,
  appendAssistant,
  waitForTtsAndPipeline: _waitForTtsAndPipeline,
}: TransitSerendipityDetourDeps) {
  const navSyncRef = useRef<NavigationSyncState | null>(null)
  const mapSnapshotRef = useRef<AgentMapSnapshot | null>(null)
  const pausePlayerXzRef = useRef<Point2 | null>(null)
  const serendipityGoalRef = useRef<Point2 | null>(null)
  const [browseScanActive, setBrowseScanActive] = useState(false)

  useEffect(() => subscribeMapCommand((command) => {
    if (command.type !== 'PAUSE_MOBILITY') return

    const ctx = contextRef.current
    if (ctx.extendedRouteActive) return
    if (ctx.transitDetourPhase !== 'idle') return

    const sync = navSyncRef.current
    if (!sync?.navigationActive) return
    if (sync.activeLeg !== 0) return

    pausePlayerXzRef.current = mapSnapshotRef.current?.playerXz ?? null

    setContext({
      transitDetourPhase: 'free_browse_scan',
      resumeLegAfterDetour: 0,
      mobilityPaused: true,
    })
    setBrowseScanActive(true)
  }), [contextRef, setContext])

  const handleFollowMeDetour = useCallback(() => {
    if (contextRef.current.transitDetourPhase !== 'paused_for_follow') return false

    const from = pausePlayerXzRef.current ?? mapSnapshotRef.current?.playerXz ?? null
    const goals = serendipityOnlyDirectGoals(from ?? undefined)
    serendipityGoalRef.current = goals[0] ?? null
    const goal = goals[0]
    recordUiMissionMessage(
      goal
        ? `[demo-debug] follow_me -> serendipity target=단 한 사람 world=(${goal[0].toFixed(2)}, ${goal[1].toFixed(2)})`
        : '[demo-debug] follow_me -> serendipity target missing',
    )

    setContext({
      transitDetourPhase: 'serendipity_nav',
      mobilityPaused: false,
    })
    setBrowseScanActive(true)
    dispatchSetDirectGoals(goals, [DEMO_BOOKS.serendipity.poolIndex])
    dispatchStartNavigation()
    return true
  }, [contextRef, setContext])

  const completeSerendipityBrowse = useCallback(
    (book: SerendipityBrowseBook) => {
      const currentPhase = contextRef.current.transitDetourPhase
      if (
        currentPhase === 'serendipity_arrived' ||
        currentPhase === 'serendipity_dwell' ||
        currentPhase === 'await_reco_accept' ||
        (currentPhase !== 'free_browse_scan' && currentPhase !== 'serendipity_nav')
      ) {
        return false
      }

      recordUiMissionMessage(
        `[demo-debug] serendipity_arrived source=camera title=${book.title}`,
      )

      const announcePromise = appendAssistant(SERENDIPITY_ARRIVAL_MESSAGE)
      announcePromise.catch((err) => {
        console.warn('[TTS] serendipity arrival guidance failed', err)
      })

      dispatchPauseMobility()
      setBrowseScanActive(false)
      setContext({
        transitDetourPhase: 'serendipity_arrived',
        mobilityPaused: true,
        pendingDwellBook: {
          booksId: DEMO_DWELL_BOOK.booksId,
          title: book.title,
          authors: book.author ?? DEMO_DWELL_BOOK.authors,
          detectedAt: Date.now(),
          source: 'cover',
        },
      })
      return true
    },
    [appendAssistant, contextRef, setContext],
  )

  const clearBrowseCountdown = useCallback(() => {
    setBrowseScanActive(false)
  }, [])

  const trackMapSnapshot = useCallback((snapshot: AgentMapSnapshot | null) => {
    mapSnapshotRef.current = snapshot
  }, [])

  useEffect(() => subscribeNavigationSync((sync) => {
    navSyncRef.current = sync
  }), [])

  return {
    browseCountdownActive: browseScanActive,
    browseCountdownBook: null,
    clearBrowseCountdown,
    completeSerendipityBrowse,
    handleFollowMeDetour,
    trackMapSnapshot,
  }
}

export { AGENT_MAP_EVENT_VERSION } from '../agent/runtime/agentEventBus'
