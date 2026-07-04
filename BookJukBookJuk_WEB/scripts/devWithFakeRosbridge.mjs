import { spawn } from 'node:child_process'

function start(label, command, args) {
  const child = spawn(command, args, {
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: false,
  })
  child.stdout.on('data', (chunk) => process.stdout.write(`[${label}] ${chunk}`))
  child.stderr.on('data', (chunk) => process.stderr.write(`[${label}] ${chunk}`))
  return child
}

const children = [
  start('fake-ros', process.execPath, [
    'scripts/fakeRosbridgeServer.mjs',
    '--speed',
    process.env.FAKE_ROS_SPEED_MPS ?? '1.6',
    '--statusHz',
    process.env.FAKE_ROS_STATUS_HZ ?? '2',
    '--idleStatusHz',
    process.env.FAKE_ROS_IDLE_STATUS_HZ ?? '0',
  ]),
  start('vite', process.execPath, ['node_modules/vite/bin/vite.js', ...process.argv.slice(2)]),
]

let shuttingDown = false

function shutdown(code = 0) {
  if (shuttingDown) return
  shuttingDown = true
  for (const child of children) {
    if (!child.killed) child.kill()
  }
  process.exit(code)
}

for (const child of children) {
  child.on('exit', (code, signal) => {
    if (shuttingDown) return
    shutdown(code ?? (signal === 'SIGTERM' ? 0 : 1))
  })
  child.on('error', (error) => {
    console.error(error)
    shutdown(1)
  })
}

process.on('SIGINT', () => shutdown(0))
process.on('SIGTERM', () => shutdown(0))
