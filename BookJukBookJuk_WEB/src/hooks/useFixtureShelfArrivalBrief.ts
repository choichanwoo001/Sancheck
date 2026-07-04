import { useEffect, useRef, type RefObject } from 'react'
import {
  AGENT_MAP_EVENT_VERSION,
  type AgentDwellEvent,
  dispatchPauseMobility,
  subscribeDwellEvent,
  subscribeMapCommand,
} from '../agent/runtime/agentEventBus'
import type { AgentContext } from '../agent/types'
import { DEMO_BOOKS, findDemoBookByTitle, type DemoBookKey } from '../data/demoScenario'
import { resolveFixtureBookForShelfArrival } from '../data/fixtureRobotRoute'
import type { PipelineItem } from './chatAgent/assistantOutputPipeline'
import { buildBookArrivalBriefItems } from './chatAgent/bookArrivalBrief'
import { claimArrivalEvent } from '../utils/arrivalDedupe'

type ShelfArrivedEvent = Extract<AgentDwellEvent, { type: 'SHELF_ARRIVED' }>

function resolveBookKeyFromArrivalEvent(event: ShelfArrivedEvent): DemoBookKey | null {
  if (event.waypointId && event.waypointId in DEMO_BOOKS) {
    return event.waypointId as DemoBookKey
  }

  if (event.label) {
    const def = findDemoBookByTitle(event.label)
    if (def) return def.key
  }

  return resolveFixtureBookForShelfArrival({
    legIndex: event.legIndex,
    poolIndex: event.poolIndex,
  }) as DemoBookKey | null
}

export type UseFixtureShelfArrivalBriefDeps = {
  enqueueAssistantMany: (items: PipelineItem[]) => Promise<void>
  appendAssistant: (text: string) => Promise<void>
  contextRef: RefObject<AgentContext>
  setContext: (patch: Partial<AgentContext>) => void
}

export function useFixtureShelfArrivalBrief(deps: UseFixtureShelfArrivalBriefDeps): void {
  const depsRef = useRef(deps)
  const navigationRunIdRef = useRef(0)
  const processedArrivalKeysRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    depsRef.current = deps
  }, [deps])

  useEffect(() => {
    return subscribeMapCommand((command) => {
      if (command.type !== 'START_NAVIGATION') return
      navigationRunIdRef.current += 1
      processedArrivalKeysRef.current.clear()
    })
  }, [])

  useEffect(() => {
    return subscribeDwellEvent((event) => {
      if (event.version !== AGENT_MAP_EVENT_VERSION) return
      if (event.type !== 'SHELF_ARRIVED') return

      const externalArrivalWithoutNavRun =
        navigationRunIdRef.current === 0 && Boolean(event.waypointId || event.label)
      const claimed =
        externalArrivalWithoutNavRun ||
        claimArrivalEvent(
          processedArrivalKeysRef.current,
          navigationRunIdRef.current,
          event,
        )
      if (!claimed) return

      const bookKey = resolveBookKeyFromArrivalEvent(event)
      if (!bookKey) return

      if (bookKey === 'serendipity') return

      const def = DEMO_BOOKS[bookKey]
      const isDemoBookStop = bookKey === 'book2' || bookKey === 'book1'
      const isActualTwoBookStop =
        depsRef.current.contextRef.current.actualTwoBookRouteActive &&
        isDemoBookStop
      const runArrivalQuestion = isDemoBookStop
      const runDwellDialogue = !runArrivalQuestion

      if (runDwellDialogue || runArrivalQuestion) {
        dispatchPauseMobility()
        depsRef.current.setContext({
          dwellDialogueActiveBookKey: bookKey as DemoBookKey,
          dwellDialogueStep: null,
          mobilityPaused: true,
          transitDetourPhase: 'idle',
          pendingDwellBook: null,
          awaitingDwellFeedback: false,
          skippedDwellBook: null,
        })
      }

      if (runArrivalQuestion) {
        void (async () => {
          depsRef.current.setContext({
            dwellDialogueActiveBookKey: bookKey as DemoBookKey,
            dwellDialogueStep: 'intro',
            mobilityPaused: true,
          })
          const briefItems = buildBookArrivalBriefItems(def, event.legIndex, {
            holdMobilityAfterBrief: true,
          })
          for (const item of briefItems) {
            await depsRef.current.appendAssistant(item.text)
          }
          if (isActualTwoBookStop && !depsRef.current.contextRef.current.actualTwoBookRouteActive) {
            return
          }
          const question =
            bookKey === 'book1'
              ? '원하는 현실적인 부분이 있는 책인가요?'
              : '직접 보시니까 어떠세요?'
          await depsRef.current.appendAssistant(question)
        })()
        return
      }

      void (async () => {
        await depsRef.current.enqueueAssistantMany(
          buildBookArrivalBriefItems(def, event.legIndex, {
            holdMobilityAfterBrief: runDwellDialogue || isActualTwoBookStop,
          }),
        )
        if (!runDwellDialogue) return

        const currentPhase = depsRef.current.contextRef.current.transitDetourPhase
        if (currentPhase !== 'idle' && currentPhase !== 'paused_for_follow') {
          return
        }

        depsRef.current.setContext({ dwellDialogueStep: 'intro' })
        await depsRef.current.appendAssistant(
          `책을 읽어보시고 다음 경로로 가고 싶으시면 "오케이"라고 말씀해 주세요.`,
        )
      })()
    })
  }, [])
}
