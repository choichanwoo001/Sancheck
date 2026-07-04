import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { RosbridgeBackend } from '../lib/verso/RosbridgeBackend'
import { registerVersoCommandBridge } from '../lib/verso/versoCommandBridge'
import type {
  VersoCommandAction,
  VersoConnectionState,
  VersoEvent,
  VersoPath,
  VersoSetModeAction,
  VersoStatus,
  VersoWaypoint,
} from '../lib/verso/types'
import {
  recordUiIncomingEvent,
  recordUiIncomingPath,
  recordUiIncomingStatus,
  recordUiOutgoingCommand,
  recordUiOutgoingWaypoints,
} from '../lib/verso/rosbridgeUiLogStore'

export type UseRobotBackendResult = {
  connectionState: VersoConnectionState
  lastStatus: VersoStatus | null
  lastPath: VersoPath | null
  lastEvent: VersoEvent | null
  /** True when rosbridge is connected and has received any robot realtime message. */
  robotSyncActive: boolean
  liveStatusRef: RefObject<VersoStatus | null>
  publishCommand: (action: VersoCommandAction) => boolean
  publishSetMode: (mode: VersoSetModeAction) => boolean
  publishWaypoints: (waypoints: VersoWaypoint[]) => boolean
  reconnect: () => void
}

/**
 * Rosbridge-only robot hook.
 * Demo and real robot flows use the same WebSocket client path; switching
 * between fake ROS and real ROS is only a rosbridge URL change.
 */
export function useRobotBackend(activeUrl: string | null): UseRobotBackendResult {
  const [connectionState, setConnectionState] = useState<VersoConnectionState>('disconnected')
  const [lastStatus, setLastStatus] = useState<VersoStatus | null>(null)
  const [lastPath, setLastPath] = useState<VersoPath | null>(null)
  const [lastEvent, setLastEvent] = useState<VersoEvent | null>(null)
  const [hasReceivedRobotData, setHasReceivedRobotData] = useState(false)
  const liveStatusRef = useRef<VersoStatus | null>(null)
  const backendRef = useRef<RosbridgeBackend | null>(null)

  const handleConnectionState = useCallback((state: VersoConnectionState) => {
    setConnectionState(state)
    if (state === 'disconnected') {
      liveStatusRef.current = null
      setLastStatus(null)
      setLastPath(null)
      setLastEvent(null)
      setHasReceivedRobotData(false)
    }
  }, [])

  const handleStatus = useCallback((status: VersoStatus) => {
    liveStatusRef.current = status
    setHasReceivedRobotData(true)
    setLastStatus(status)
    recordUiIncomingStatus(status)
  }, [])

  const handlePath = useCallback((path: VersoPath) => {
    setHasReceivedRobotData(true)
    setLastPath(path)
    recordUiIncomingPath(path)
  }, [])

  const handleEvent = useCallback((event: VersoEvent) => {
    setHasReceivedRobotData(true)
    setLastEvent(event)
    recordUiIncomingEvent(event)
  }, [])

  const publishCommand = useCallback((action: VersoCommandAction): boolean => {
    const ok = backendRef.current?.publishCommand(action) ?? false
    if (ok) recordUiOutgoingCommand(action)
    return ok
  }, [])

  const publishSetMode = useCallback((mode: VersoSetModeAction): boolean => {
    const ok = backendRef.current?.publishSetMode(mode) ?? false
    if (ok) recordUiOutgoingCommand(mode)
    return ok
  }, [])

  const publishWaypoints = useCallback((waypoints: VersoWaypoint[]): boolean => {
    setLastPath(null)
    const ok = backendRef.current?.publishWaypoints(waypoints) ?? false
    if (ok) recordUiOutgoingWaypoints(waypoints)
    return ok
  }, [])

  const reconnect = useCallback((): void => {
    backendRef.current?.reconnect()
  }, [])

  useEffect(() => {
    const trimmed = activeUrl?.trim() ?? ''

    backendRef.current?.destroy()
    backendRef.current = null

    if (trimmed) {
      const backend = new RosbridgeBackend()
      backend.setHandlers({
        onConnectionState: handleConnectionState,
        onStatus: handleStatus,
        onPath: handlePath,
        onEvent: handleEvent,
      })
      backend.start(trimmed)
      backendRef.current = backend
    } else {
      handleConnectionState('disconnected')
    }

    return () => {
      backendRef.current?.destroy()
      backendRef.current = null
    }
  }, [activeUrl, handleConnectionState, handleEvent, handlePath, handleStatus])

  const robotSyncActive = connectionState === 'connected' && hasReceivedRobotData

  useEffect(() => {
    registerVersoCommandBridge(
      connectionState,
      robotSyncActive,
      robotSyncActive ? publishCommand : null,
      robotSyncActive ? publishSetMode : null,
      robotSyncActive ? publishWaypoints : null,
    )
    return () => registerVersoCommandBridge('disconnected', false, null, null, null)
  }, [connectionState, publishCommand, publishSetMode, publishWaypoints, robotSyncActive])

  return useMemo(
    () => ({
      connectionState,
      lastStatus,
      lastPath,
      lastEvent,
      robotSyncActive,
      liveStatusRef,
      publishCommand,
      publishSetMode,
      publishWaypoints,
      reconnect,
    }),
    [
      connectionState,
      lastStatus,
      lastPath,
      lastEvent,
      hasReceivedRobotData,
      robotSyncActive,
      publishCommand,
      publishSetMode,
      publishWaypoints,
      reconnect,
    ],
  )
}
