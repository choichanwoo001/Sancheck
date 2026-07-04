import { WebSocket, WebSocketServer } from 'ws'

const TOPICS = {
  status: '/verso/status',
  path: '/verso/path',
  event: '/verso/event',
  command: '/verso/command',
  waypoints: '/verso/waypoints',
}

const args = new Map()
for (let i = 2; i < process.argv.length; i += 1) {
  const key = process.argv[i]
  if (!key?.startsWith('--')) continue
  const next = process.argv[i + 1]
  args.set(key.slice(2), next?.startsWith('--') || next === undefined ? 'true' : next)
  if (next && !next.startsWith('--')) i += 1
}

const port = Number(args.get('port') ?? 9090)
const host = args.get('host') ?? '127.0.0.1'
const statusHz = Number(args.get('statusHz') ?? 1)
const idleStatusHz = Number(args.get('idleStatusHz') ?? statusHz)
const tickHz = Number(args.get('tickHz') ?? 20)
const speedMps = Number(args.get('speed') ?? 1.6)
const arrivalRadiusM = Number(args.get('arrivalRadius') ?? 0.15)
const statusIntervalMs = statusHz > 0 ? Math.max(100, Math.round(1000 / statusHz)) : null
const idleStatusIntervalMs =
  idleStatusHz > 0 ? Math.max(100, Math.round(1000 / idleStatusHz)) : null
const tickIntervalMs = Math.max(16, Math.round(1000 / tickHz))

const state = {
  // Match ROBOT_MAP_START in src/lib/verso/robotMissionCoords.ts.
  x: Number(args.get('x') ?? -21.987),
  y: Number(args.get('y') ?? 6.568),
  heading: Number(args.get('heading') ?? 0),
  mode: 'guidance',
  isMoving: false,
  waypoints: [],
}

const wss = new WebSocketServer({ host, port })
const subscriptions = new WeakMap()
let lastIdleStatusAt = 0

function now() {
  return new Date().toISOString()
}

function log(message, detail) {
  const suffix = detail === undefined ? '' : ` ${JSON.stringify(detail)}`
  console.log(`[${now()}] ${message}${suffix}`)
}

function rosPublish(topic, payload) {
  return JSON.stringify({
    op: 'publish',
    topic,
    msg: { data: JSON.stringify(payload) },
  })
}

function sendIfSubscribed(ws, topic, payload) {
  const topics = subscriptions.get(ws)
  if (!topics?.has(topic) || ws.readyState !== WebSocket.OPEN) return
  ws.send(rosPublish(topic, payload))
}

function broadcast(topic, payload) {
  for (const ws of wss.clients) {
    sendIfSubscribed(ws, topic, payload)
  }
}

function statusPayload() {
  return {
    type: 'status',
    position: {
      x: state.x,
      y: state.y,
      heading: state.heading,
    },
    mode: state.mode,
    is_moving: state.isMoving,
    current_waypoint_id: state.waypoints[0]?.id ?? null,
    remaining_waypoints: state.waypoints.length,
  }
}

function pathPayload() {
  return {
    type: 'path',
    poses: [
      { x: state.x, y: state.y },
      ...state.waypoints.map((wp) => ({ x: wp.x, y: wp.y })),
    ],
  }
}

function eventPayload(event, waypoint) {
  return {
    type: 'event',
    event,
    waypoint_id: waypoint?.id,
    label: waypoint?.label,
  }
}

function publishStatusAndPath() {
  broadcast(TOPICS.status, statusPayload())
  broadcast(TOPICS.path, pathPayload())
}

function publishPeriodicStatus() {
  if (state.isMoving) {
    broadcast(TOPICS.status, statusPayload())
    return
  }
  if (idleStatusIntervalMs === null) return
  const current = Date.now()
  if (current - lastIdleStatusAt < idleStatusIntervalMs) return
  lastIdleStatusAt = current
  broadcast(TOPICS.status, statusPayload())
}

function parseDataMessage(raw) {
  try {
    const frame = JSON.parse(String(raw))
    if (!frame || typeof frame !== 'object') return null
    return frame
  } catch {
    return null
  }
}

function parsePayload(frame) {
  const data = frame?.msg?.data
  if (typeof data !== 'string') return null
  try {
    return JSON.parse(data)
  } catch {
    return null
  }
}

function distanceSq(a, b) {
  const dx = a.x - b.x
  const dy = a.y - b.y
  return dx * dx + dy * dy
}

function sortWaypointsNearestFirst(waypoints) {
  const finalWaypoint =
    waypoints.at(-1)?.id === 'checkout' ? waypoints[waypoints.length - 1] : null
  const remaining = finalWaypoint ? waypoints.slice(0, -1) : waypoints.slice()
  const sorted = []
  let cursor = { x: state.x, y: state.y }

  while (remaining.length > 0) {
    let bestIndex = 0
    let bestDistance = distanceSq(cursor, remaining[0])
    for (let i = 1; i < remaining.length; i += 1) {
      const candidateDistance = distanceSq(cursor, remaining[i])
      if (candidateDistance < bestDistance) {
        bestIndex = i
        bestDistance = candidateDistance
      }
    }
    const [next] = remaining.splice(bestIndex, 1)
    sorted.push(next)
    cursor = next
  }

  if (finalWaypoint) sorted.push(finalWaypoint)
  return sorted
}

function setWaypoints(waypoints) {
  const normalizedWaypoints = waypoints
    .filter((wp) => Number.isFinite(wp?.x) && Number.isFinite(wp?.y))
    .map((wp, index) => ({
      id: String(wp.id ?? `wp_${index}`),
      x: Number(wp.x),
      y: Number(wp.y),
      label: typeof wp.label === 'string' ? wp.label : undefined,
    }))

  state.waypoints = sortWaypointsNearestFirst(normalizedWaypoints)
  state.mode = 'escort'
  state.isMoving = state.waypoints.length > 0
  publishStatusAndPath()
}

function applyCommand(payload) {
  if (payload?.action === 'set_mode' && typeof payload.mode === 'string') {
    state.mode = payload.mode
    if (payload.mode === 'escort') state.isMoving = state.waypoints.length > 0
    if (payload.mode === 'guidance') state.isMoving = false
    broadcast(TOPICS.status, statusPayload())
    return
  }

  if (payload?.action === 'stop') {
    state.mode = 'stopped'
    state.isMoving = false
    broadcast(TOPICS.status, statusPayload())
    return
  }

  if (payload?.action === 'resume') {
    state.mode = 'escort'
    state.isMoving = state.waypoints.length > 0
    broadcast(TOPICS.status, statusPayload())
    return
  }

  if (payload?.action === 'end_session') {
    state.mode = 'guidance'
    state.isMoving = false
    state.waypoints = []
    if (Number.isFinite(payload.x) && Number.isFinite(payload.y)) {
      state.x = Number(payload.x)
      state.y = Number(payload.y)
    }
    publishStatusAndPath()
    broadcast(TOPICS.event, eventPayload('home_reached'))
    broadcast(TOPICS.event, eventPayload('session_ended'))
  }
}

function advanceMotion(deltaSeconds) {
  if (!state.isMoving || state.waypoints.length === 0) return

  const target = state.waypoints[0]
  const dx = target.x - state.x
  const dy = target.y - state.y
  const distance = Math.hypot(dx, dy)
  state.heading = Math.atan2(dy, dx)

  const step = Math.max(0, speedMps * deltaSeconds)
  if (distance <= Math.max(arrivalRadiusM, step)) {
    state.x = target.x
    state.y = target.y
    const arrived = state.waypoints.shift()
    state.mode = 'stopped'
    state.isMoving = false
    log('waypoint arrived', arrived)
    broadcast(TOPICS.event, eventPayload('waypoint_arrived', arrived))
    publishStatusAndPath()
    return
  }

  state.x += (dx / distance) * step
  state.y += (dy / distance) * step
}

wss.on('connection', (ws, req) => {
  subscriptions.set(ws, new Set())
  log('client connected', { remote: req.socket.remoteAddress })

  ws.on('message', (raw) => {
    const frame = parseDataMessage(raw)
    if (!frame) {
      log('ignored invalid frame')
      return
    }

    if (frame.op === 'subscribe' && typeof frame.topic === 'string') {
      subscriptions.get(ws)?.add(frame.topic)
      log('subscribe', { topic: frame.topic })
      if (frame.topic === TOPICS.status) sendIfSubscribed(ws, TOPICS.status, statusPayload())
      if (frame.topic === TOPICS.path) sendIfSubscribed(ws, TOPICS.path, pathPayload())
      return
    }

    if (frame.op !== 'publish' || typeof frame.topic !== 'string') {
      log('ignored unsupported frame', frame)
      return
    }

    const payload = parsePayload(frame)
    log('publish received', { topic: frame.topic, payload })

    if (frame.topic === TOPICS.command) {
      applyCommand(payload)
      return
    }

    if (frame.topic === TOPICS.waypoints && Array.isArray(payload?.waypoints)) {
      setWaypoints(payload.waypoints)
    }
  })

  ws.on('close', () => {
    log('client disconnected')
  })
})

let lastTick = Date.now()
const movementTimer = setInterval(() => {
  const current = Date.now()
  const deltaSeconds = Math.min(0.25, (current - lastTick) / 1000)
  lastTick = current
  advanceMotion(deltaSeconds)
}, tickIntervalMs)

const statusTimer =
  statusIntervalMs === null
    ? null
    : setInterval(() => {
        publishPeriodicStatus()
      }, statusIntervalMs)

function shutdown() {
  clearInterval(movementTimer)
  if (statusTimer) clearInterval(statusTimer)
  wss.close(() => process.exit(0))
}

process.on('SIGINT', shutdown)
process.on('SIGTERM', shutdown)

wss.on('close', () => {
  clearInterval(movementTimer)
  if (statusTimer) clearInterval(statusTimer)
})

log('fake rosbridge listening', {
  url: `ws://${host}:${port}`,
  statusHz,
  idleStatusHz,
  tickHz,
  speedMps,
})
