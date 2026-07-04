import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { isVersoConnected, publishVersoResume } from '../lib/verso/versoMobilityCommands'
import { logActualTwoBookOkDispatch, logMissionNavStart } from '../lib/verso/rosbridgeConnectionLog'
import {
  parseUserIntent,
  toolCallForIntent,
} from '../agent/runtime/chatAgentRuntime'
import {
  isListEditIntentType,
  mergePlannerIntentWithRules,
  requiresConfirmation,
} from '../agent/policy'
import { transitionStateFromIntent } from '../agent/stateMachine'
import {
  getTelemetrySnapshot,
  incrementMetric,
  recordIntentOutcome,
} from '../agent/telemetry'
import {
  AGENT_MAP_EVENT_VERSION,
  dispatchDwellEvent,
  dispatchSetDirectGoals,
  dispatchPreviewNavPlan,
  dispatchStartNavigation,
  subscribeDwellEvent,
  subscribeMapCommand,
  subscribeMapSnapshot,
  dispatchMobilityHold,
  type AgentMapSnapshot,
} from '../agent/runtime/agentEventBus'
import {
  createAssistantOutputPipeline,
  type AssistantOutputPipeline,
  type PipelineItem,
} from './chatAgent/assistantOutputPipeline'
import { useTts } from './useTts'
import { planWithLlm } from '../agent/runtime/llmPlanner'
import { normalizeListHint } from '../agent/listHintNormalize'
import type {
  AgentContext,
  AgentIntentType,
  AgentIntentSource,
  AgentMessage,
  DwellBookCandidate,
  RecognitionKind,
  ShoppingListEntry,
  ToolExecutionContext,
  ToolResult,
} from '../agent/types'
import { appendUserMessageAndStore } from './chatAgent/helpers'
import { mergePlannedToolCall } from './chatAgent/toolCallMerge'
import { useExistingListGate } from './chatAgent/useExistingListGate'
import { isProceedToken } from './chatAgent/proceedToken'
import { resolvePendingConfirmationReply } from './chatAgent/pendingConfirmationReply'
import { buildNavStartPrompt, CHAT_AGENT_MESSAGES } from './chatAgent/messages'
import { resolveUnknownChatReply } from './chatAgent/resolveUnknownChatReply'
import type { TasteSeed } from '../types/onboarding'
import { useFixtureShelfArrivalBrief } from './useFixtureShelfArrivalBrief'
import {
  fixtureRobotDirectGoals,
  SERENDIPITY_BROWSE_POOL_INDEX,
} from '../data/fixtureRobotRoute'
import {
  DEMO_BOOKS,
  DEMO_DWELL_BOOK,
  DEMO_RECOMMENDED_BOOK,
  demoBookToEntry,
  demoRefCoverUrl,
  findDemoBookByTitle,
  type DemoBookKey,
} from '../data/demoScenario'
import { useToolRunner } from './chatAgent/useToolRunner'
import { useChatAgentSession } from './chatAgent/useChatAgentSession'
import { completeCheckoutPurchase } from '../agent/tools/checkoutCompletion'
import { checkoutTool } from '../agent/tools/checkoutTool'
import { useTransitSerendipityDetour } from './useTransitSerendipityDetour'

function hasSerendipityBook(list: ShoppingListEntry[]): boolean {
  const serendipityId = DEMO_DWELL_BOOK.booksId
  return list.some(
    (item) =>
      item.booksId === serendipityId || findDemoBookByTitle(item.title)?.key === 'serendipity',
  )
}

const ACTUAL_TWO_BOOK_ROUTE_KEYS: DemoBookKey[] = ['book2', 'book1']
const ACTUAL_STOP_OK_ROBOT_ROUTE_KEYS: DemoBookKey[] = ['book2']

function isBookEntryForKey(item: ShoppingListEntry, key: DemoBookKey): boolean {
  const def = DEMO_BOOKS[key]
  return item.booksId === def.fallbackBooksId || findDemoBookByTitle(item.title)?.key === key
}

function uniqueByBooksId(items: ShoppingListEntry[]): ShoppingListEntry[] {
  const seen = new Set<string>()
  const next: ShoppingListEntry[] = []
  for (const item of items) {
    if (seen.has(item.booksId)) continue
    seen.add(item.booksId)
    next.push(item)
  }
  return next
}

function actualTwoBookVisitList(current: ShoppingListEntry[]): ShoppingListEntry[] {
  const routeEntries = ACTUAL_TWO_BOOK_ROUTE_KEYS.map((key) => {
    return current.find((item) => isBookEntryForKey(item, key)) ?? demoBookToEntry(DEMO_BOOKS[key])
  })
  return uniqueByBooksId(routeEntries)
}

function addActualRouteBookToCart(
  cartItems: ShoppingListEntry[],
  visitList: ShoppingListEntry[],
  key: DemoBookKey,
): ShoppingListEntry[] {
  const exists = cartItems.some((item) => isBookEntryForKey(item, key))
  if (exists) return cartItems
  const entry = visitList.find((item) => isBookEntryForKey(item, key)) ?? demoBookToEntry(DEMO_BOOKS[key])
  return [...cartItems, entry]
}

function hasActualRouteBook(cartItems: ShoppingListEntry[], key: DemoBookKey): boolean {
  return cartItems.some((item) => isBookEntryForKey(item, key))
}

const initialContextValue = (): AgentContext => ({
  state: 'INIT',
  mobilityPaused: false,
  listType: '쇼핑리스트',
  activeUsersId: undefined,
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
})

const initialMessages: AgentMessage[] = []
const ASSISTANT_MESSAGE_APPEAR_DELAY_MS = 1000
const LONG_ASSISTANT_MESSAGE_APPEAR_DELAY_MS = 2000
const LONG_ASSISTANT_MESSAGE_MIN_LENGTH = 120

function extractRecommendationTitles(result: ToolResult | null): string[] {
  if (!result?.ok || result.toolName !== 'recommendationTool') return []
  const lines = (result.data as { recommendations?: unknown } | undefined)?.recommendations
  if (!Array.isArray(lines)) return []
  return lines
    .map((line) => {
      if (typeof line !== 'string') return ''
      const body = line.replace(/^[^0-9]*\d+\.\s*/, '')
      const [title] = body.split(/\s-\s/)
      return title.trim()
    })
    .filter((title) => title.length > 0)
}

function extractRecommendationCandidates(result: ToolResult | null): ShoppingListEntry[] {
  if (!result?.ok || result.toolName !== 'recommendationTool') return []
  const candidates = (result.data as { candidates?: unknown } | undefined)?.candidates
  if (!Array.isArray(candidates)) return []
  const rows: Array<ShoppingListEntry | null> = candidates
    .map((item) => {
      if (!item || typeof item !== 'object') return null
      const row = item as { booksId?: unknown; title?: unknown; authors?: unknown; coverImageUrl?: unknown }
      const booksId = String(row.booksId ?? '').trim()
      const title = String(row.title ?? '').trim()
      if (!booksId || !title) return null
      const coverImageUrl = typeof row.coverImageUrl === 'string' ? row.coverImageUrl.trim() : ''
      const demoBook = findDemoBookByTitle(title)
      return {
        booksId,
        title,
        authors: typeof row.authors === 'string' ? row.authors : '',
        coverImageUrl: coverImageUrl || (demoBook ? demoRefCoverUrl(demoBook) : ''),
      }
    })
  return rows.filter((item): item is ShoppingListEntry => item !== null)
}

function parseRecommendationPickIndex(text: string): number | null {
  const numeric = text.match(/(\d+)\s*번/)
  if (numeric) return Number.parseInt(numeric[1], 10) - 1
  if (text.includes('첫')) return 0
  if (text.includes('둘') || text.includes('두')) return 1
  if (text.includes('셋') || text.includes('세')) return 2
  if (text.includes('넷') || text.includes('네')) return 3
  if (text.includes('다섯')) return 4
  return null
}

function createAssistant(text: string, attachments?: string[]): AgentMessage {
  return {
    id: crypto.randomUUID(),
    role: 'assistant',
    text,
    attachments,
    createdAt: Date.now(),
  }
}

function getAssistantMessageAppearDelayMs(text: string): number {
  return text.trim().length >= LONG_ASSISTANT_MESSAGE_MIN_LENGTH
    ? LONG_ASSISTANT_MESSAGE_APPEAR_DELAY_MS
    : ASSISTANT_MESSAGE_APPEAR_DELAY_MS
}

function waitForAssistantMessageAppearDelay(text: string): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, getAssistantMessageAppearDelayMs(text))
  })
}

export function resolveVisibleDwellDialogueFromMessages(
  history: AgentMessage[],
): { bookKey: DemoBookKey; step: 'intro' | 'feedback' } | null {
  for (let i = history.length - 1; i >= 0; i -= 1) {
    const message = history[i]
    if (message.role !== 'assistant') continue
    const text = message.text.trim()

    if (text === '직접 보시니까 어떠세요?' || text === '어떠세요?') {
      return { bookKey: 'book2', step: 'intro' }
    }
    if (text.includes('원하는 현실적인 부분') && text.includes('책인가요')) {
      return { bookKey: 'book1', step: 'intro' }
    }
    if (text.includes('사실건가요')) {
      if (text.includes(DEMO_BOOKS.book2.authors)) return { bookKey: 'book2', step: 'feedback' }
      if (text.includes(DEMO_BOOKS.book1.authors)) return { bookKey: 'book1', step: 'feedback' }
    }

    return null
  }
  return null
}

const VALID_INTENT_TYPES: AgentIntentType[] = [
  'select_browse_mode',
  'search_books',
  'pause_mobility',
  'resume_mobility',
  'follow_robot',
  'lead_robot',
  'checkout',
  'add_book',
  'remove_book',
  'route_replan_shortest',
  'request_recommendation',
  'confirm',
  'cancel',
  'unknown',
]

function asIntentType(input: string): AgentIntentType {
  return (VALID_INTENT_TYPES as string[]).includes(input) ? (input as AgentIntentType) : 'unknown'
}


export function useChatAgent(options: {
  initialShoppingList?: ShoppingListEntry[]
  tasteSeed?: TasteSeed | null
}) {
  const [messages, setMessages] = useState<AgentMessage[]>(initialMessages)
  const messagesRef = useRef<AgentMessage[]>(messages)
  const [context, setContextState] = useState<AgentContext>(initialContextValue)
  const contextRef = useRef<AgentContext>(context)
  const [latestMapSnapshot, setLatestMapSnapshot] = useState<AgentMapSnapshot | null>(null)
  const [busy, setBusy] = useState(false)
  const [lastFailedUserText, setLastFailedUserText] = useState<string | null>(null)
  const dwellTimerRef = useRef<number | null>(null)
  const dwellKeyRef = useRef<string | null>(null)
  const tts = useTts()
  const [mobilityHold, setMobilityHold] = useState(false)
  const applyMobilityHold = useCallback((held: boolean) => {
    dispatchMobilityHold(held)
    setMobilityHold(held)
  }, [])
  const pipelineRef = useRef<AssistantOutputPipeline | null>(null)
  const ttsSpeaking = false

  const waitForTtsAndPipeline = useCallback(async () => {
    while (
      (pipelineRef.current && (pipelineRef.current.getQueueLength() > 0 || pipelineRef.current.isProcessing()))
    ) {
      await new Promise((resolve) => setTimeout(resolve, 100))
    }
  }, [])
  const hasInitialShoppingList = (options.initialShoppingList?.length ?? 0) > 0
  const shouldAutoLoadShelf = !hasInitialShoppingList
  const { gateRef: existingListGateRef, updateGate: updateExistingListGate } = useExistingListGate()
  const checkoutArrivalHandledRef = useRef(false)
  const kakaoCheckoutInFlightRef = useRef(false)
  const kakaoConfirmInFlightRef = useRef(false)
  const navStartPromptShownRef = useRef(false)
  useLayoutEffect(() => {
    contextRef.current = context
  }, [context])

  useLayoutEffect(() => {
    messagesRef.current = messages
  }, [messages])

  /**
   * Same-tick `contextRef` sync is required because `submitUserText` reads
   * `contextRef.current` immediately after a state change in async flows.
   */
  const setContext = useCallback((patch: Partial<AgentContext>) => {
    contextRef.current = { ...contextRef.current, ...patch }
    setContextState((prev) => {
      const next = { ...prev, ...patch }
      contextRef.current = next
      return next
    })
  }, [])

  useEffect(() => subscribeMapSnapshot(setLatestMapSnapshot), [])

  useEffect(() => {
    return subscribeDwellEvent((event) => {
      if (event.type === 'DWELL_BOOK_DETECTED') {
        setContext({ pendingDwellBook: event.book })
      }
    })
  }, [setContext])

  useEffect(() => {
    return subscribeDwellEvent((event) => {
      if (event.type !== 'SHELF_ARRIVED') return

      // browse 스톱(단 한 사람)에 도착하면 타이머 없이 즉시 dwell 감지.
      // extendedRouteActive이면 이미 경로 확장이 완료된 상태이므로 재감지 건너뜀.
      if (
        event.poolIndex === SERENDIPITY_BROWSE_POOL_INDEX &&
        !contextRef.current.extendedRouteActive
      ) {
        if (dwellTimerRef.current !== null) window.clearTimeout(dwellTimerRef.current)
        const book: DwellBookCandidate = {
          booksId: DEMO_DWELL_BOOK.booksId,
          title: DEMO_DWELL_BOOK.title,
          authors: DEMO_DWELL_BOOK.authors,
          detectedAt: Date.now(),
          source: 'route',
        }
        dispatchDwellEvent({ type: 'DWELL_BOOK_DETECTED', version: AGENT_MAP_EVENT_VERSION, book })
        return
      }

      // 일반 스톱: 이전 추천 결과의 후보를 30초 후 dwell 감지 (기존 로직).
      const candidates = extractRecommendationCandidates(contextRef.current.lastToolResult)
      if (candidates.length === 0) return

      const candidate = candidates[Math.abs(event.legIndex) % candidates.length]
      if (!candidate) return
      const key = `${latestMapSnapshot?.missionVersion ?? 0}:${event.legIndex}:${candidate.booksId}`
      if (dwellKeyRef.current === key) return

      if (dwellTimerRef.current !== null) window.clearTimeout(dwellTimerRef.current)
      dwellKeyRef.current = key
      dwellTimerRef.current = window.setTimeout(() => {
        const book: DwellBookCandidate = {
          ...candidate,
          detectedAt: Date.now(),
          source: 'route',
        }
        dispatchDwellEvent({ type: 'DWELL_BOOK_DETECTED', version: AGENT_MAP_EVENT_VERSION, book })
      }, 30000)
    })
  }, [latestMapSnapshot?.missionVersion])

  const {
    appendAssistantConversationMessage,
    conversationIdRef,
    listLoadMessage,
    listLoadStatus,
    sessionReady,
  } = useChatAgentSession({
    initialShoppingList: options.initialShoppingList,
    listType: context.listType,
    setContext,
    setMessages,
    shouldAutoLoadShelf,
  })

  const toolExecutionContext = useMemo<ToolExecutionContext>(
    () => ({
      getContext: () => contextRef.current,
      setContext,
    }),
    [setContext],
  )

  const appendAssistant = useCallback((text: string, attachments?: string[]) => {
    setMessages((prev) => [...prev, createAssistant(text, attachments)])
  }, [])

  const appendAssistantDirectRef = useRef(
    async (text: string, attachments?: string[]) => {
      await waitForAssistantMessageAppearDelay(text)
      appendAssistant(text, attachments)
      await appendAssistantConversationMessage(text)
    },
  )

  useLayoutEffect(() => {
    appendAssistantDirectRef.current = async (text: string, attachments?: string[]) => {
      await waitForAssistantMessageAppearDelay(text)
      appendAssistant(text, attachments)
      await appendAssistantConversationMessage(text)
    }
  }, [appendAssistant, appendAssistantConversationMessage])

  const pipeline = useMemo(
    () =>
      createAssistantOutputPipeline({
        appendAssistant: (text, attachments) => appendAssistantDirectRef.current(text, attachments),
        speakAndWait: async () => {},
        isTtsEnabled: () => false,
        onMobilityHoldChange: applyMobilityHold,
        onResumeMobility: () => publishVersoResume(),
      }),
    [applyMobilityHold],
  )

  useLayoutEffect(() => {
    pipelineRef.current = pipeline
    return () => {
      pipeline.dispose()
      pipelineRef.current = null
    }
  }, [pipeline])

  const enqueueAssistant = useCallback(
    (item: PipelineItem) => pipeline.enqueue({ ...item, stream: item.stream ?? false }),
    [pipeline],
  )

  const enqueueAssistantMany = useCallback(
    (items: PipelineItem[]) =>
      pipeline.enqueueMany(items.map((item) => ({ ...item, stream: item.stream ?? false }))),
    [pipeline],
  )

  const appendAssistantAndStore = useCallback(
    async (text: string, attachments?: string[]) => {
      await enqueueAssistant({ text, attachments, gate: { kind: 'immediate' } })
    },
    [enqueueAssistant],
  )

  const appendAssistantUrgent = useCallback(async (text: string, attachments?: string[]) => {
    await appendAssistantDirectRef.current(text, attachments)
  }, [])

  const resolveNavStartBookCount = useCallback(() => {
    const listCount = contextRef.current.shoppingList.length
    if (listCount > 0) return listCount
    return options.initialShoppingList?.length ?? 0
  }, [options.initialShoppingList])

  /** 현재 쇼핑리스트(또는 카트)에서 데모 도서 poolIndex 배열을 반환. 데모 경로 결정에 사용. */
  const resolveCurrentPoolIndices = useCallback((): number[] | null => {
    const list =
      contextRef.current.shoppingList.length > 0
          ? contextRef.current.shoppingList
          : (options.initialShoppingList ?? [])
    if (list.length === 0) return null
    const indices = list
      .map((entry) => findDemoBookByTitle(entry.title)?.poolIndex)
      .filter((idx): idx is number => idx !== undefined)
    return indices.length > 0 ? indices : null
  }, [options.initialShoppingList])

  const resolveRobotPoolIndicesForNavigation = useCallback((poolIndices: number[]): number[] => {
    const book2PoolIndex = DEMO_BOOKS.book2.poolIndex
    const book1PoolIndex = DEMO_BOOKS.book1.poolIndex
    if (
      contextRef.current.actualTwoBookRouteActive &&
      poolIndices.includes(book2PoolIndex) &&
      poolIndices.includes(book1PoolIndex)
    ) {
      return ACTUAL_STOP_OK_ROBOT_ROUTE_KEYS.map((key) => DEMO_BOOKS[key].poolIndex)
    }
    return poolIndices
  }, [])

  const resolveNavStartItems = useCallback((): ShoppingListEntry[] => {
    if (contextRef.current.shoppingList.length > 0) return contextRef.current.shoppingList
    return options.initialShoppingList ?? []
  }, [options.initialShoppingList])

  const ensureNavStartPromptShown = useCallback(async () => {
    const bookCount = resolveNavStartBookCount()
    if (bookCount === 0) return
    if (navStartPromptShownRef.current) return
    const navPrompt = buildNavStartPrompt(bookCount)
    if (messagesRef.current.some((message) => message.role === 'assistant' && message.text === navPrompt)) {
      if (existingListGateRef.current.status === 'inactive') {
        updateExistingListGate({ status: 'awaiting_nav' })
      }
      navStartPromptShownRef.current = true
      return
    }
    if (existingListGateRef.current.status === 'inactive') {
      updateExistingListGate({ status: 'awaiting_nav' })
    }
    navStartPromptShownRef.current = true
    await appendAssistantAndStore(navPrompt)
  }, [
    appendAssistantAndStore,
    existingListGateRef,
    resolveNavStartBookCount,
    updateExistingListGate,
  ])

  const {
    browseCountdownActive,
    browseCountdownBook,
    clearBrowseCountdown,
    completeSerendipityBrowse,
    handleFollowMeDetour,
    trackMapSnapshot,
  } = useTransitSerendipityDetour({
    contextRef,
    setContext,
    appendAssistant: appendAssistantUrgent,
    waitForTtsAndPipeline,
  })

  useEffect(() => {
    trackMapSnapshot(latestMapSnapshot)
  }, [latestMapSnapshot, trackMapSnapshot])

  useEffect(() => {
    return subscribeMapCommand((command) => {
      if (command.type !== 'START_NAVIGATION') return
      checkoutArrivalHandledRef.current = false
      applyMobilityHold(false)
      pipelineRef.current?.resetNavRun()
    })
  }, [applyMobilityHold])

  useEffect(() => {
    if (resolveNavStartBookCount() === 0) return
    if (existingListGateRef.current.status === 'nav_started') return
    const poolIndices = resolveCurrentPoolIndices()
    if (poolIndices && poolIndices.length > 0) {
      dispatchPreviewNavPlan(fixtureRobotDirectGoals(poolIndices))
    } else if (!hasInitialShoppingList && !sessionReady) {
      return
    }
    void ensureNavStartPromptShown()
  }, [
    context.cartItems.length,
    context.shoppingList.length,
    ensureNavStartPromptShown,
    existingListGateRef,
    hasInitialShoppingList,
    options.initialShoppingList?.length,
    resolveCurrentPoolIndices,
    resolveNavStartBookCount,
    sessionReady,
  ])

  useEffect(() => {
    return subscribeMapCommand((command) => {
      if (command.type !== 'PREVIEW_NAV_PLAN') return
      void ensureNavStartPromptShown()
    })
  }, [ensureNavStartPromptShown])

  useEffect(() => {
    return subscribeDwellEvent((event) => {
      if (event.type !== 'CHECKOUT_ARRIVED') return
      if (checkoutArrivalHandledRef.current) return
      const cartItems = contextRef.current.cartItems
      if (cartItems.length === 0) return

      checkoutArrivalHandledRef.current = true
      void (async () => {
        if (contextRef.current.checkoutStatus === 'going_to_counter') {
          setContext({ checkoutStatus: 'idle' })
          await enqueueAssistant({
            text: '계산대에 도착했어요. 오른쪽 구매 리스트의 계산하기 버튼으로 결제를 진행하시면 됩니다.',
            gate: { kind: 'on_checkout_arrived' },
          })
          return
        }

        const result = await completeCheckoutPurchase(toolExecutionContext)
        if (result.ok) {
          await enqueueAssistant({
            text: result.message,
            gate: { kind: 'on_checkout_arrived' },
          })
        } else {
          await appendAssistantAndStore(result.message)
          checkoutArrivalHandledRef.current = false
        }
      })()
    })
  }, [appendAssistantAndStore, enqueueAssistant, setContext, toolExecutionContext])

  const appendRecognitionMessage = useCallback((kind: RecognitionKind, text: string) => {
    const message: AgentMessage = {
      id: crypto.randomUUID(),
      role: 'recognition',
      text,
      recognitionKind: kind,
      createdAt: Date.now(),
    }
    setMessages((prev) => [...prev, message])
  }, [])

  useFixtureShelfArrivalBrief({
    enqueueAssistantMany,
    appendAssistant: appendAssistantUrgent,
    contextRef,
    setContext,
  })

  /**
   * Shared post-execute pipeline used by both the `confirm` flow and the
   * regular intent flow: telemetry → context patch (incl. transitioned state)
   * → assistant message → fallbackTool on failure.
   */
  const runToolWithFallback = useToolRunner({
    toolExecutionContext,
    contextRef,
    setContext,
    appendAssistantAndStore,
  })

  const markActualStopRouteExtensionPending = useCallback(() => {
    if (!isVersoConnected()) return
    if (contextRef.current.transitDetourPhase === 'free_browse_scan') return

    setContext({
      actualStopRouteExtensionPending: false,
      actualTwoBookRouteActive: false,
      mobilityPaused: true,
      transitDetourPhase: 'free_browse_scan',
      pendingDwellBook: null,
      awaitingDwellFeedback: false,
      skippedDwellBook: null,
      dwellDialogueActiveBookKey: null,
      dwellDialogueStep: null,
    })
    void appendAssistantAndStore(
      '정지했습니다. 직접 둘러보는 동안 책 표지를 인식할게요.',
    )
  }, [appendAssistantAndStore, setContext])

  const startActualTwoBookRouteAfterStop = useCallback(async () => {
    const nextVisitList = actualTwoBookVisitList(contextRef.current.shoppingList)
    const robotPoolIndices = ACTUAL_STOP_OK_ROBOT_ROUTE_KEYS.map(
      (key) => DEMO_BOOKS[key].poolIndex,
    )

    setContext({
      shoppingList: nextVisitList,
      actualStopRouteExtensionPending: false,
      actualTwoBookRouteActive: true,
      extendedRouteActive: true,
      mobilityPaused: false,
      pendingDwellBook: null,
      awaitingDwellFeedback: false,
      skippedDwellBook: null,
      transitDetourPhase: 'idle',
      dwellDialogueActiveBookKey: null,
      dwellDialogueStep: null,
    })
    updateExistingListGate({ status: 'nav_started' })
    logMissionNavStart('ok_proceed', ACTUAL_STOP_OK_ROBOT_ROUTE_KEYS.length)
    logActualTwoBookOkDispatch(ACTUAL_STOP_OK_ROBOT_ROUTE_KEYS.map((key) => DEMO_BOOKS[key].title))
    dispatchSetDirectGoals(fixtureRobotDirectGoals(robotPoolIndices), robotPoolIndices)
    dispatchStartNavigation()
    await appendAssistantAndStore(
      '좋습니다. 방문 목록에는 오직 두 사람과 어른이 된다는 것을 넣고, 먼저 오직 두 사람 좌표를 로봇에게 전달했어요.',
    )
  }, [appendAssistantAndStore, setContext, updateExistingListGate])

  const continueActualTwoBookRouteByOk = useCallback(async (confirmedBookKey?: DemoBookKey | null) => {
    const visitList = actualTwoBookVisitList(contextRef.current.shoppingList)

    if (confirmedBookKey === 'book1') {
      const nextCart = addActualRouteBookToCart(
        contextRef.current.cartItems,
        visitList,
        'book1',
      )

      setContext({
        shoppingList: visitList,
        cartItems: nextCart,
        actualStopRouteExtensionPending: false,
        actualTwoBookRouteActive: false,
        extendedRouteActive: false,
        mobilityPaused: false,
        pendingDwellBook: null,
        awaitingDwellFeedback: false,
        skippedDwellBook: null,
        transitDetourPhase: 'idle',
        dwellDialogueActiveBookKey: null,
        dwellDialogueStep: null,
        checkoutStatus: 'idle',
      })
      await appendAssistantUrgent(
        '구매 리스트에 추가했어요. 구매를 완료하셨으면 계산하기 버튼을 클릭해주세요.',
      )
      return
    }

    if (confirmedBookKey === 'book2' || !hasActualRouteBook(contextRef.current.cartItems, 'book2')) {
      const nextCart = addActualRouteBookToCart(
        contextRef.current.cartItems,
        visitList,
        'book2',
      )
      const book1PoolIndex = DEMO_BOOKS.book1.poolIndex

      setContext({
        shoppingList: visitList,
        cartItems: nextCart,
        actualStopRouteExtensionPending: false,
        actualTwoBookRouteActive: true,
        extendedRouteActive: true,
        mobilityPaused: false,
        pendingDwellBook: null,
        awaitingDwellFeedback: false,
        skippedDwellBook: null,
        transitDetourPhase: 'idle',
        dwellDialogueActiveBookKey: null,
        dwellDialogueStep: null,
      })
      logMissionNavStart('ok_proceed', 1)
      dispatchSetDirectGoals(fixtureRobotDirectGoals([book1PoolIndex]), [book1PoolIndex])
      dispatchStartNavigation()
      await appendAssistantUrgent(
        '구매 리스트에 추가했어요. 다음 목적지로 이동할게요.',
      )
      return
    }

    setContext({
      actualStopRouteExtensionPending: false,
      actualTwoBookRouteActive: false,
      mobilityPaused: false,
      dwellDialogueActiveBookKey: null,
      dwellDialogueStep: null,
      checkoutStatus: 'idle',
    })
    await appendAssistantUrgent('구매를 완료하셨으면 계산하기 버튼을 클릭해주세요.')
  }, [appendAssistantUrgent, setContext])

  const applyExtendedRouteAfterReco = useCallback(async () => {
    const skippedBook = contextRef.current.skippedDwellBook
    if (!skippedBook) return

    const candidates = extractRecommendationCandidates(contextRef.current.lastToolResult)
    const recoBook = candidates[0] ?? DEMO_RECOMMENDED_BOOK

    const currentVisitList = resolveNavStartItems()
    const hasOriginalBook = currentVisitList.some((book) => findDemoBookByTitle(book.title)?.key === 'book2')
    const visitListWithOriginal = hasOriginalBook
      ? currentVisitList
      : [
          ...currentVisitList,
          demoBookToEntry(DEMO_BOOKS.book2),
        ]
    const nextVisitList = visitListWithOriginal.some((book) => book.booksId === recoBook.booksId)
      ? visitListWithOriginal
      : [
          ...visitListWithOriginal,
          {
            booksId: recoBook.booksId,
            title: recoBook.title,
            authors: recoBook.authors,
            coverImageUrl: recoBook.coverImageUrl,
          },
        ]
    const robotPoolIndices = ACTUAL_STOP_OK_ROBOT_ROUTE_KEYS.map(
      (key) => DEMO_BOOKS[key].poolIndex,
    )
    setContext({
      shoppingList: nextVisitList,
      skippedDwellBook: null,
      extendedRouteActive: true,
      actualTwoBookRouteActive: true,
      actualStopRouteExtensionPending: false,
      mobilityPaused: false,
      transitDetourPhase: 'idle',
      resumeLegAfterDetour: null,
      dwellDialogueActiveBookKey: null,
      dwellDialogueStep: null,
    })
    updateExistingListGate({ status: 'awaiting_nav' })
    dispatchSetDirectGoals(fixtureRobotDirectGoals(robotPoolIndices), robotPoolIndices)
    dispatchStartNavigation()
    await appendAssistantAndStore(
      `좋아요. 방문 목록에는 「${DEMO_BOOKS.book2.title}」와 추천한 「${recoBook.title}」을 넣고, 가까운 「${DEMO_BOOKS.book2.title}」 좌표만 로봇에게 전달했어요.`,
    )
  }, [
    appendAssistantAndStore,
    resolveNavStartItems,
    setContext,
    updateExistingListGate,
  ])

  const handleCancelIntent = useCallback(async () => {
    const pending = contextRef.current.pendingConfirmation
    if (!pending) {
      await appendAssistantAndStore('취소할 확인 대기가 없어요.')
      recordIntentOutcome('cancel', true)
      return
    }
    setContext({ pendingConfirmation: null })
    await appendAssistantAndStore('요청을 취소했어요.')
    recordIntentOutcome('cancel', true)
  }, [appendAssistantAndStore, setContext])

  const handleConfirmIntent = useCallback(async () => {
    const pending = contextRef.current.pendingConfirmation
    if (!pending) {
      await appendAssistantAndStore('확인할 작업이 없어요.')
      recordIntentOutcome('confirm', false)
      return
    }
    await runToolWithFallback(
      { name: pending.toolName, args: pending.args },
      'confirm',
      { pendingConfirmation: null },
    )
  }, [appendAssistantAndStore, runToolWithFallback])

  const submitUserText = useCallback(
    async (text: string, source: AgentIntentSource = 'chat') => {
      const normalized = text.replace(/\r\n/g, '\n')
      const intentText = normalized.trim()
      if (!intentText) return

      setBusy(true)
      setLastFailedUserText(null)
      try {
        const visibleDwellDialogue = resolveVisibleDwellDialogueFromMessages(messagesRef.current)
        const dwellDialogueBookKey =
          contextRef.current.dwellDialogueActiveBookKey ?? visibleDwellDialogue?.bookKey ?? null
        const dwellDialogueStep =
          contextRef.current.dwellDialogueStep ?? visibleDwellDialogue?.step ?? null

        if (
          isVersoConnected() &&
          contextRef.current.actualStopRouteExtensionPending &&
          isProceedToken(intentText)
        ) {
          await appendUserMessageAndStore({
            text: normalized,
            conversationId: conversationIdRef.current,
            intent: 'confirm',
            setMessages,
          })
          await startActualTwoBookRouteAfterStop()
          return
        }

        if (
          contextRef.current.actualTwoBookRouteActive &&
          dwellDialogueStep === 'feedback' &&
          isProceedToken(intentText)
        ) {
          const confirmedBookKey = dwellDialogueBookKey
          await appendUserMessageAndStore({
            text: normalized,
            conversationId: conversationIdRef.current,
            intent: 'confirm',
            setMessages,
          })
          await continueActualTwoBookRouteByOk(confirmedBookKey)
          return
        }

        // 1. Dwell Dialogue Step 1 ("직접 보시니까 어떠세요?" -> feedback)
        if (
          dwellDialogueBookKey &&
          dwellDialogueStep === 'intro'
        ) {
          const bookKey = dwellDialogueBookKey
          const def = DEMO_BOOKS[bookKey]
          await appendUserMessageAndStore({
            text: normalized,
            conversationId: conversationIdRef.current,
            intent: 'unknown',
            setMessages,
          })

          setContext({
            dwellDialogueActiveBookKey: bookKey,
            dwellDialogueStep: 'feedback',
          })

          const tastePhrase = bookKey === 'book1' ? '현실적인 측면을' : '따뜻한 문체를'
          await appendAssistantUrgent(
            `사용자님이 ${def.authors} 작가의 ${tastePhrase} 좋아할 줄 알았어요. 사실건가요?`,
          )
          return
        }

        // 2. Dwell Dialogue Step 2 ("사실건가요?" -> resume check)
        if (
          dwellDialogueBookKey &&
          dwellDialogueStep === 'feedback' &&
          isProceedToken(intentText)
        ) {
          const bookKey = dwellDialogueBookKey
          const def = DEMO_BOOKS[bookKey]
          const isBookInCart = contextRef.current.cartItems.some(
            (item) => item.booksId === def.fallbackBooksId || findDemoBookByTitle(item.title)?.key === bookKey
          )

          await appendUserMessageAndStore({
            text: normalized,
            conversationId: conversationIdRef.current,
            intent: 'confirm',
            setMessages,
          })

          if (bookKey === 'book1') {
            await continueActualTwoBookRouteByOk('book1')
            return
          }

          if (isBookInCart) {
            setContext({
              dwellDialogueActiveBookKey: null,
              dwellDialogueStep: null,
              mobilityPaused: false,
            })
            publishVersoResume()
            await appendAssistantUrgent('좋습니다. 다음 목적지로 안내를 계속할게요.')
          } else {
            await appendAssistantUrgent(
              `아직 "${def.title}" 책이 장바구니에 담기지 않았습니다. 책 표지 인식이나 제스처로 책을 담으신 후 다시 "오케이"라고 말씀해주세요.`
            )
          }
          return
        }

        // 3. Serendipity Shelf resume check
        if (
          contextRef.current.transitDetourPhase === 'serendipity_arrived' &&
          isProceedToken(intentText)
        ) {
          await appendUserMessageAndStore({
            text: normalized,
            conversationId: conversationIdRef.current,
            intent: 'confirm',
            setMessages,
          })

          const isSerendipityInList =
            hasSerendipityBook(contextRef.current.cartItems) ||
            hasSerendipityBook(contextRef.current.shoppingList)

          if (!isSerendipityInList) {
            const dwellBook: DwellBookCandidate =
              contextRef.current.pendingDwellBook?.booksId === DEMO_DWELL_BOOK.booksId
                ? contextRef.current.pendingDwellBook
                : {
                    booksId: DEMO_DWELL_BOOK.booksId,
                    title: DEMO_DWELL_BOOK.title,
                    authors: DEMO_DWELL_BOOK.authors,
                    detectedAt: Date.now(),
                    source: 'cover',
                  }
            setContext({
              transitDetourPhase: 'serendipity_dwell',
              pendingDwellBook: dwellBook,
              awaitingDwellFeedback: true,
              mobilityPaused: true,
            })
            clearBrowseCountdown()
            await appendAssistantUrgent(
              '왜 단 한 사람 책을 구매 리스트에 안담았나요?',
            )
          } else {
            await appendAssistantUrgent(
              `"${DEMO_DWELL_BOOK.title}" 책을 장바구니에 담으셨군요! 원래 목적지인 "${DEMO_BOOKS.book2.title}" 서가로 다시 출발하겠습니다.`
            )
            await waitForTtsAndPipeline()
            setContext({
              transitDetourPhase: 'idle',
              mobilityPaused: false,
            })
            clearBrowseCountdown()
            const book2PoolIndex = DEMO_BOOKS.book2.poolIndex
            dispatchSetDirectGoals(fixtureRobotDirectGoals([book2PoolIndex]), [book2PoolIndex])
            dispatchStartNavigation()
          }
          return
        }

        if (contextRef.current.awaitingDwellFeedback && contextRef.current.pendingDwellBook) {
          const dwellBook = contextRef.current.pendingDwellBook
          await appendUserMessageAndStore({
            text: normalized,
            conversationId: conversationIdRef.current,
            intent: 'request_recommendation',
            setMessages,
          })

          if (
            contextRef.current.transitDetourPhase === 'serendipity_dwell'
          ) {
            const recoBook = DEMO_RECOMMENDED_BOOK
            const recoResult: ToolResult = {
              ok: true,
              toolName: 'recommendationTool',
              message: `"${recoBook.title}"을 추천드려요.`,
              data: {
                recommendations: [`보완 추천 1. ${recoBook.title} - ${recoBook.authors}`],
                source: 'demo_transit_detour',
                candidates: [{
                  booksId: recoBook.booksId,
                  title: recoBook.title,
                  authors: recoBook.authors,
                }],
              },
            }
            setContext({
              awaitingDwellFeedback: false,
              skippedDwellBook: dwellBook,
              pendingDwellBook: null,
              transitDetourPhase: 'await_reco_accept',
              lastToolResult: recoResult,
            })
            await appendAssistantUrgent(
              `말씀하신 걸 보면 「${DEMO_DWELL_BOOK.title}」의 한 사람에게 깊게 집중하는 정서와 관계의 온도는 잘 맞았지만, 지금은 조금 더 현실에서 바로 붙잡을 수 있는 조언이 필요해 보여요. 그래서 그 감정선은 유지하면서 관계와 책임을 더 실용적으로 풀어낸 「${recoBook.title}」을 추천할게요. 관심 있으신가요?`,
              [`보완 추천 1. ${recoBook.title} - ${recoBook.authors}`],
            )
            return
          }

          // skippedDwellBook에 보존: 추천 결과 후 "경로에 추가" 요청 시 함께 추가하기 위함.
          setContext({ awaitingDwellFeedback: false, skippedDwellBook: dwellBook })
          await runToolWithFallback(
            {
              name: 'recommendationTool',
              args: {
                mode: 'book_alternative',
                seedBookId: dwellBook.booksId,
                negativeReason: intentText,
              },
            },
            'request_recommendation',
            { pendingDwellBook: null },
          )
          return
        }

        const cartForNav = resolveNavStartItems()
        const canStartNavigationFromProceed =
          !contextRef.current.pendingConfirmation &&
          contextRef.current.transitDetourPhase === 'idle' &&
          !contextRef.current.awaitingDwellFeedback &&
          isProceedToken(intentText) &&
          cartForNav.length > 0

        if (canStartNavigationFromProceed) {
          const poolIndices = resolveCurrentPoolIndices()
          if (!poolIndices || poolIndices.length === 0) {
            await appendAssistantAndStore(
              '현재 목록에서 로봇 목적지 좌표를 찾지 못했습니다. 목적지 좌표가 있는 책을 선택한 뒤 다시 안내를 시작해 주세요.',
            )
            recordIntentOutcome('confirm', false)
            return
          }
          await appendUserMessageAndStore({
            text: normalized,
            conversationId: conversationIdRef.current,
            intent: 'confirm',
            setMessages,
          })
          const robotPoolIndices = resolveRobotPoolIndicesForNavigation(poolIndices)
          updateExistingListGate({ status: 'nav_started' })
          logMissionNavStart('ok_proceed', robotPoolIndices.length)
          dispatchSetDirectGoals(fixtureRobotDirectGoals(robotPoolIndices), robotPoolIndices)
          dispatchStartNavigation()
          void appendAssistantAndStore('안내를 시작할게요.')
          return
        }

        if (contextRef.current.pendingConfirmation) {
          const pendingReply = resolvePendingConfirmationReply(intentText)
          if (pendingReply === 'confirm') {
            await appendUserMessageAndStore({
              text: normalized,
              conversationId: conversationIdRef.current,
              intent: 'confirm',
              setMessages,
            })
            setContext({
              state: transitionStateFromIntent(contextRef.current.state, 'confirm'),
            })
            await handleConfirmIntent()
            return
          }
          if (pendingReply === 'cancel') {
            await appendUserMessageAndStore({
              text: normalized,
              conversationId: conversationIdRef.current,
              intent: 'cancel',
              setMessages,
            })
            setContext({
              state: transitionStateFromIntent(contextRef.current.state, 'cancel'),
            })
            await handleCancelIntent()
            return
          }
        }

        // transit detour: dwell 피드백 후 "오케이"로 확장 경로 수락
        if (
          contextRef.current.transitDetourPhase === 'await_reco_accept' &&
          isProceedToken(intentText) &&
          contextRef.current.skippedDwellBook &&
          contextRef.current.lastToolResult?.toolName === 'recommendationTool'
        ) {
          await appendUserMessageAndStore({
            text: normalized,
            conversationId: conversationIdRef.current,
            intent: 'confirm',
            setMessages,
          })
          await applyExtendedRouteAfterReco()
          return
        }

        // 경로 확장: dwell 피드백 후 추천 수락 시 어른이 된다는 것 추가 + 오직 두 사람 안내 재개.
        if (
          contextRef.current.skippedDwellBook &&
          !contextRef.current.extendedRouteActive &&
          contextRef.current.lastToolResult?.toolName === 'recommendationTool' &&
          /(경로|같이|함께|두\s*(권|책))/.test(intentText)
        ) {
          await appendUserMessageAndStore({
            text: normalized,
            conversationId: conversationIdRef.current,
            intent: 'add_book',
            setMessages,
          })
          await applyExtendedRouteAfterReco()
          return
        }

        const llmPlan = await planWithLlm({
          text: intentText,
          source,
          context: contextRef.current,
          history: messagesRef.current,
        })
        const parsedIntent = parseUserIntent(intentText, source)
        const llmIntentType = llmPlan ? asIntentType(llmPlan.intentType) : 'unknown'
        const hasUsableLlmIntent = llmPlan !== null && llmIntentType !== 'unknown'
        const nextIntent = mergePlannerIntentWithRules({
          ruleIntent: parsedIntent,
          llmPlan,
          rawTextForLlm: text,
          source,
          llmIntentType,
          hasUsableLlmIntent,
        })
        if (
          hasUsableLlmIntent &&
          isListEditIntentType(parsedIntent.type) &&
          llmIntentType !== parsedIntent.type
        ) {
          incrementMetric('listEditRuleOverridesLlm')
        }
        if (hasUsableLlmIntent) incrementMetric('llmPlannerUsed')
        else incrementMetric('llmPlannerFallback')
        const mergedIntent = nextIntent

        await appendUserMessageAndStore({
          text: normalized,
          conversationId: conversationIdRef.current,
          intent: mergedIntent.type,
          setMessages,
        })

        setContext({
          state: transitionStateFromIntent(contextRef.current.state, mergedIntent.type),
        })

        if (mergedIntent.type === 'cancel') {
          await handleCancelIntent()
          return
        }

        if (mergedIntent.type === 'confirm') {
          await handleConfirmIntent()
          return
        }

        if (mergedIntent.type === 'resume_mobility') {
          const dwellBook = contextRef.current.pendingDwellBook
          const isInCart = dwellBook ? contextRef.current.cartItems.some((item) => item.booksId === dwellBook.booksId) : false
          if (dwellBook && !isInCart) {
            setContext({ awaitingDwellFeedback: true, mobilityPaused: true })
            await appendAssistantAndStore(
              `"${dwellBook.title}"에 관심을 보이셨는데 장바구니에 담지 않으셨네요. 어떤 점이 마음에 걸리셨는지 말씀해 주시면 그 책 기준으로 더 잘 맞는 책을 추천해드릴게요.`,
            )
            return
          }
        }

        if (mergedIntent.type === 'follow_robot') {
          if (contextRef.current.transitDetourPhase === 'paused_for_follow') {
            if (handleFollowMeDetour()) {
              recordIntentOutcome('follow_robot', true)
              return
            }
          }
        }

        if (mergedIntent.type === 'select_browse_mode') {
          setContext({ listType: '쇼핑리스트' })
          await appendAssistantAndStore(
            '계획 없이 바로 출발합니다. 화면에 보이는 추천이나 제가 말해드리는 추천에 집중해 주세요. 필요하면 "추천해줘"라고 말해 주세요. 마음에 들면 쇼핑리스트에 담을 수 있어요.',
          )
          recordIntentOutcome('select_browse_mode', true)
          return
        }

        const deterministicToolCall = toolCallForIntent(mergedIntent)
        const plannedToolCall = mergedIntent.type === 'unknown' ? null : (llmPlan?.toolCall ?? null)
        let toolCall = mergePlannedToolCall(deterministicToolCall, plannedToolCall, mergedIntent.type)
        if (mergedIntent.type === 'add_book' && toolCall?.name === 'shoppingListTool') {
          const index = parseRecommendationPickIndex(intentText)
          if (index != null) {
            const titles = extractRecommendationTitles(contextRef.current.lastToolResult)
            const title = titles[index]
            if (title) {
              toolCall = {
                ...toolCall,
                args: { ...toolCall.args, hint: `책 추가 ${title}` },
              }
            }
          }
        }
        if (!toolCall) {
          if (mergedIntent.type === 'unknown') {
            const unknownReply = await resolveUnknownChatReply({
              text: intentText,
              llmPlan,
              context: contextRef.current,
              history: messagesRef.current,
            })
            if (unknownReply.kind === 'off_topic') incrementMetric('chatOffTopicReply')
            else if (unknownReply.usedLlm) incrementMetric('chatConversationalLlmUsed')
            else incrementMetric('chatConversationalLlmFallback')
            await appendAssistantAndStore(unknownReply.text)
            recordIntentOutcome('unknown', unknownReply.kind === 'conversational')
            return
          }
          await appendAssistantAndStore('현재 이 요청은 아직 연결되지 않았어요.')
          recordIntentOutcome(mergedIntent.type, false)
          return
        }

        if (requiresConfirmation(mergedIntent)) {
          incrementMetric('reconfirmRequested')
          let summary = `${mergedIntent.rawText} 요청을 실행할까요? 확인 버튼을 누르거나 "오케이"라고 입력하면 진행합니다.`
          if (mergedIntent.type === 'remove_book' && toolCall.name === 'shoppingListTool') {
            const rawHint = typeof toolCall.args.hint === 'string' ? toolCall.args.hint : mergedIntent.rawText
            const interpretedTitle = normalizeListHint(rawHint, 'remove')
            if (interpretedTitle) {
              summary = `"${interpretedTitle}" 삭제 요청을 실행할까요? 확인 버튼을 누르거나 "오케이"라고 입력하면 진행합니다.`
            }
          }
          setContext({
            pendingConfirmation: {
              toolName: toolCall.name,
              args: toolCall.args,
              summary,
            },
          })
          await appendAssistantAndStore(summary.replace('확인 버튼을 누르거나 "오케이"라고 입력하면 진행합니다.', '카드에서 확인하거나 오케이라고 입력해 주세요.'))
          return
        }

        if (mergedIntent.type === 'pause_mobility' || mergedIntent.type === 'resume_mobility') {
          incrementMetric('interruptHandled')
        }

        let result = await runToolWithFallback(toolCall, mergedIntent.type)
        if (
          !result.ok &&
          result.errorCode === 'VALIDATION_ERROR' &&
          deterministicToolCall &&
          (deterministicToolCall.name !== toolCall.name ||
            JSON.stringify(deterministicToolCall.args) !== JSON.stringify(toolCall.args))
        ) {
          result = await runToolWithFallback(deterministicToolCall, mergedIntent.type)
        }

        if (!result.ok) {
          setLastFailedUserText(normalized)
        }

        /**
         * Behavior preserved: this reads `contextRef.current.state` *after*
         * `runToolWithFallback` has already transitioned it, matching the
         * pre-refactor semantics (sessionCompleted fires when the
         * post-transition state is GOAL_CHECK and the tool succeeded).
         */
        if (contextRef.current.state === 'GOAL_CHECK' && result.ok) {
          incrementMetric('sessionCompleted')
        }
      } finally {
        setBusy(false)
      }
    },
    [
      appendAssistantAndStore,
      appendAssistantUrgent,
      enqueueAssistant,
      handleCancelIntent,
      handleConfirmIntent,
      conversationIdRef,
      runToolWithFallback,
      setContext,
      existingListGateRef,
      updateExistingListGate,
      applyExtendedRouteAfterReco,
      startActualTwoBookRouteAfterStop,
      continueActualTwoBookRouteByOk,
      handleFollowMeDetour,
      resolveCurrentPoolIndices,
      resolveRobotPoolIndicesForNavigation,
      resolveNavStartItems,
    ],
  )

  const acceptConfirmation = useCallback(() => {
    void submitUserText(CHAT_AGENT_MESSAGES.confirmInput, 'chat')
  }, [submitUserText])

  const cancelConfirmation = useCallback(() => {
    void submitUserText(CHAT_AGENT_MESSAGES.cancelInput, 'chat')
  }, [submitUserText])

  const retryLastFailed = useCallback(() => {
    if (!lastFailedUserText) return
    void submitUserText(lastFailedUserText, 'chat')
  }, [lastFailedUserText, submitUserText])

  /** Multimodal / alternate source (W18). */
  const submitAgentInput = useCallback(
    (text: string, source: AgentIntentSource) => {
      void submitUserText(text, source)
    },
    [submitUserText],
  )

  const applyBookGestureDecision = useCallback(
    async (reason: 'add' | 'remove', book: { title: string; author?: string }) => {
      setBusy(true)
      setLastFailedUserText(null)
      try {
        const label = reason === 'add' ? '제스처 · 담기' : '제스처 · 빼기'
        await appendUserMessageAndStore({
          text: `[${label}] ${book.title}`,
          conversationId: conversationIdRef.current,
          intent: reason === 'add' ? 'add_book' : 'remove_book',
          setMessages,
        })
        const intentType = reason === 'add' ? 'add_book' : 'remove_book'
        const verb = reason === 'add' ? '추가' : '삭제'
        const result = await runToolWithFallback(
          {
            name: 'shoppingListTool',
            args: { action: reason, hint: `책 ${verb} ${book.title}`, source: 'gesture' },
          },
          intentType,
        )
        if (!result.ok) {
          setLastFailedUserText(`[${label}] ${book.title}`)
        }
      } finally {
        setBusy(false)
      }
    },
    [conversationIdRef, runToolWithFallback, setMessages],
  )

  const applyBookRecognitionCapture = useCallback(
    async (
      reason: 'add' | 'remove' | 'browse',
      imageBase64: string,
      trigger: 'gesture' | 'ui' = 'ui',
    ) => {
      if (!imageBase64.trim()) return
      if (reason === 'browse') {
        setBusy(true)
        try {
          await appendUserMessageAndStore({
            text: '[표지 인식 · 구경]',
            conversationId: conversationIdRef.current,
            intent: 'unknown',
            setMessages,
          })
        } finally {
          setBusy(false)
        }
        return
      }
      setBusy(true)
      setLastFailedUserText(null)
      try {
        const label =
          trigger === 'gesture'
            ? reason === 'add'
              ? '제스처 · 담기'
              : '제스처 · 빼기'
            : reason === 'add'
              ? '표지 인식 · 담기'
              : '표지 인식 · 빼기'
        await appendUserMessageAndStore({
          text: `[${label}]`,
          conversationId: conversationIdRef.current,
          intent: reason === 'add' ? 'add_book' : 'remove_book',
          setMessages,
        })
        const intentType = reason === 'add' ? 'add_book' : 'remove_book'
        const result = await runToolWithFallback(
          { name: 'shoppingListTool', args: { action: reason, imageBase64, source: trigger } },
          intentType,
        )
        if (!result.ok) {
          setLastFailedUserText(`[${label}]`)
        }
      } finally {
        setBusy(false)
      }
    },
    [conversationIdRef, runToolWithFallback, setMessages],
  )

  const applyBookBrowseCapture = useCallback(
    async (imageBase64: string) => {
      await applyBookRecognitionCapture('browse', imageBase64)
    },
    [applyBookRecognitionCapture],
  )

  const startKakaoPayCheckout = useCallback(async () => {
    if (kakaoCheckoutInFlightRef.current || contextRef.current.kakaoPaySession) return
    kakaoCheckoutInFlightRef.current = true
    try {
      const result = await checkoutTool.run({}, toolExecutionContext)
      await appendAssistantAndStore(result.message)
    } finally {
      kakaoCheckoutInFlightRef.current = false
    }
  }, [appendAssistantAndStore, toolExecutionContext])

  const confirmKakaoPayCheckout = useCallback(async () => {
    if (!contextRef.current.kakaoPaySession) return
    if (contextRef.current.checkoutStatus === 'completed') return
    if (kakaoConfirmInFlightRef.current) return
    kakaoConfirmInFlightRef.current = true
    try {
      const result = await completeCheckoutPurchase(toolExecutionContext, { preferLocalFirst: true })
      await appendAssistantAndStore(result.message)
    } finally {
      kakaoConfirmInFlightRef.current = false
    }
  }, [appendAssistantAndStore, toolExecutionContext])

  const cancelKakaoPayCheckout = useCallback(() => {
    setContext({ kakaoPaySession: null, checkoutStatus: 'idle' })
  }, [setContext])

  return {
    messages,
    submitUserText,
    submitAgentInput,
    markActualStopRouteExtensionPending,
    appendRecognitionMessage,
    applyBookRecognitionCapture,
    applyBookGestureDecision,
    applyBookBrowseCapture,
    demoBrowseCountdownActive: browseCountdownActive,
    demoBrowseCountdownBook: browseCountdownBook,
    completeSerendipityBrowse,
    handleFollowMeDetour,
    startKakaoPayCheckout,
    confirmKakaoPayCheckout,
    cancelKakaoPayCheckout,
    context,
    latestMapSnapshot,
    telemetry: getTelemetrySnapshot(),
    busy,
    lastFailedUserText,
    acceptConfirmation,
    cancelConfirmation,
    retryLastFailed,
    listLoadStatus,
    listLoadMessage,
    tts,
    ttsSpeaking,
    mobilityHold,
  }
}
