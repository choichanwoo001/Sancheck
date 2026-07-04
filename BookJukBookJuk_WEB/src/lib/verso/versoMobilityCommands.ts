import { AGENT_MAP_EVENT_VERSION, dispatchMapCommand, dispatchPauseMobility } from '../../agent/runtime/agentEventBus'
import {
  isVersoRobotSyncActive,
  tryPublishVersoCommand,
  tryPublishVersoSetMode,
} from './versoCommandBridge'
import { ROBOT_MAP_START } from './robotMissionCoords'

export function isVersoConnected(): boolean {
  return isVersoRobotSyncActive()
}

export function publishVersoStop(): boolean {
  const published = tryPublishVersoCommand('stop')
  dispatchPauseMobility()
  return published
}

export function publishVersoResume(): boolean {
  const published = tryPublishVersoCommand('resume')
  dispatchMapCommand({ type: 'RESUME_MOBILITY', version: AGENT_MAP_EVENT_VERSION })
  return published
}

export function publishVersoEndSession(): boolean {
  return tryPublishVersoCommand({
    action: 'end_session',
    x: ROBOT_MAP_START.x,
    y: ROBOT_MAP_START.y,
  })
}

export function publishVersoGuidance(): boolean {
  return tryPublishVersoSetMode('guidance')
}

export function publishVersoEscort(): boolean {
  return tryPublishVersoSetMode('escort')
}
