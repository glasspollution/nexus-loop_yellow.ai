import { spawn } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const screenDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const appDir = resolve(screenDir, '..')
const expectedOutDir = resolve(appDir, 'out', 'practice')
const expectedKitDir = resolve(appDir, '..', 'kit')
const localBackendBaseUrl = 'http://127.0.0.1:8765'
const configuredBaseUrl = (process.env.VITE_API_BASE_URL ?? '').trim().replace(/\/+$/, '')
const backendBaseUrl = configuredBaseUrl || localBackendBaseUrl
const backendHealthUrl = `${backendBaseUrl}/api/health`
const configuredReplayUrl = (process.env.NEXUS_REPLAY_URL ?? '').trim().replace(/\/+$/, '')
const localReplayBaseUrl = 'http://127.0.0.1:8719'
const replayBaseUrl = configuredReplayUrl || localReplayBaseUrl
const replayHealthUrl = `${replayBaseUrl}/health`
const healthTimeoutMs = 1_000

function validateBackendUrl() {
  let url
  try {
    url = new URL(backendHealthUrl)
  } catch {
    throw new Error('VITE_API_BASE_URL must be an absolute http:// or https:// URL when using npm run dev.')
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error('VITE_API_BASE_URL must be an absolute http:// or https:// URL when using npm run dev.')
  }
}

function samePath(left, right) {
  if (typeof left !== 'string' || typeof right !== 'string') return false
  const paths = [left, right].map((value) => resolve(value))
  return process.platform === 'win32'
    ? paths[0].toLowerCase() === paths[1].toLowerCase()
    : paths[0] === paths[1]
}

function validateExpectedCorpus(health) {
  if (health.mode !== 'live-session') {
    throw new Error(
      'Port 8765 is serving an older persistent backend. Stop it, then rerun npm run dev to start the live session.',
    )
  }
  if (!samePath(health.out_dir, expectedOutDir)) {
    throw new Error(
      `Port 8765 is serving a different analysis (${health.out_dir}). ` +
      `Stop that backend or start it with --out "${expectedOutDir}".`,
    )
  }
  if (!samePath(health.kit_dir, expectedKitDir)) {
    throw new Error(
      `Port 8765 is analysing a different corpus (${health.kit_dir ?? 'unknown'}). ` +
        `Stop that backend or start it with --kit "${expectedKitDir}".`,
    )
  }
  if (health.replay_configured !== true) {
    throw new Error('Port 8765 is not connected to a replay engine. Stop it, then rerun npm run dev.')
  }
}

async function readJsonHealth(url) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), healthTimeoutMs)
  try {
    const response = await fetch(url, { cache: 'no-store', signal: controller.signal })
    if (!response.ok) return { kind: 'invalid', reason: `health check returned HTTP ${response.status}` }
    const body = await response.json()
    return body?.ok === true
      ? { kind: 'ready', body }
      : { kind: 'invalid', reason: 'health response did not report ready' }
  } catch (error) {
    return {
      kind: 'unreachable',
      reason: controller.signal.aborted
        ? `health check timed out after ${healthTimeoutMs}ms`
        : error instanceof Error ? error.message : 'health check failed',
    }
  } finally {
    clearTimeout(timeout)
  }
}

async function readBackendHealth() {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), healthTimeoutMs)
  try {
    const response = await fetch(backendHealthUrl, {
      cache: 'no-store',
      signal: controller.signal,
    })
    if (!response.ok) {
      return { kind: 'invalid', reason: `health check returned HTTP ${response.status}` }
    }
    const body = await response.json()
    if (body?.ok !== true || typeof body.out_dir !== 'string') {
      return { kind: 'invalid', reason: 'health response is not from a Nexus Loop backend' }
    }
    return { kind: 'ready', body }
  } catch (error) {
    const reason = controller.signal.aborted
      ? `health check timed out after ${healthTimeoutMs}ms`
      : error instanceof Error
        ? error.message
        : 'health check failed'
    return { kind: 'unreachable', reason }
  } finally {
    clearTimeout(timeout)
  }
}

function childStopped(child) {
  return child.exitCode != null || child.signalCode != null
}

async function waitForBackend(child, getSpawnError) {
  const deadline = Date.now() + 10_000
  let lastReason = 'not ready'
  while (Date.now() < deadline) {
    const health = await readBackendHealth()
    if (health.kind === 'ready') {
      validateExpectedCorpus(health.body)
      return
    }
    lastReason = health.reason
    const spawnError = getSpawnError()
    if (spawnError) throw new Error(`Could not start the backend: ${spawnError.message}`)
    if (childStopped(child)) {
      const detail = child.exitCode != null ? `exit code ${child.exitCode}` : `signal ${child.signalCode}`
      throw new Error(`Backend stopped with ${detail}.`)
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 100))
  }
  throw new Error(`Backend did not become ready on ${backendBaseUrl} (${lastReason}).`)
}

let backend = null
let replay = null
let frontend = null
let stopping = false

function stop(signal = 'SIGTERM') {
  if (stopping) return
  stopping = true
  if (frontend && !childStopped(frontend)) frontend.kill(signal)
  if (backend && !childStopped(backend)) backend.kill(signal)
  if (replay && !childStopped(replay)) replay.kill(signal)
}

async function ensureReplay() {
  const initial = await readJsonHealth(replayHealthUrl)
  if (initial.kind === 'ready') {
    process.stdout.write(`Using the replay engine already running on ${replayBaseUrl}.\n`)
    return
  }
  if (configuredReplayUrl) {
    throw new Error(`Configured replay engine ${replayBaseUrl} is not ready (${initial.reason}).`)
  }
  if (initial.kind === 'invalid') {
    throw new Error(`Port 8719 is not serving a usable replay engine (${initial.reason}).`)
  }

  let spawnError = null
  const replayScript = resolve(appDir, '..', 'tools', 'nexus-loop-kit', 'replay', 'serve.py')
  replay = spawn('python', [replayScript, '--kit', expectedKitDir, '--port', '8719'], {
    cwd: appDir,
    stdio: 'inherit',
  })
  replay.once('error', (error) => { spawnError = error })
  const deadline = Date.now() + 10_000
  let lastReason = initial.reason
  while (Date.now() < deadline) {
    const health = await readJsonHealth(replayHealthUrl)
    if (health.kind === 'ready') return
    lastReason = health.reason
    if (spawnError) throw new Error(`Could not start the replay engine: ${spawnError.message}`)
    if (childStopped(replay)) {
      const detail = replay.exitCode != null ? `exit code ${replay.exitCode}` : `signal ${replay.signalCode}`
      throw new Error(`Replay engine stopped with ${detail}.`)
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 100))
  }
  throw new Error(`Replay engine did not become ready on ${replayBaseUrl} (${lastReason}).`)
}

async function main() {
  validateBackendUrl()
  if (!configuredBaseUrl) await ensureReplay()
  const initialHealth = await readBackendHealth()

  if (configuredBaseUrl) {
    if (initialHealth.kind !== 'ready') {
      throw new Error(`Configured backend ${backendBaseUrl} is not ready (${initialHealth.reason}).`)
    }
    process.stdout.write(`Using the configured Nexus Loop backend on ${backendBaseUrl}.\n`)
  } else if (initialHealth.kind === 'ready') {
    validateExpectedCorpus(initialHealth.body)
    process.stdout.write(`Using the Nexus Loop backend already running on ${localBackendBaseUrl}.\n`)
  } else if (initialHealth.kind === 'invalid') {
    throw new Error(`Port 8765 is not serving a usable Nexus Loop backend (${initialHealth.reason}).`)
  } else {
    let spawnError = null
    backend = spawn(
      'python',
      ['server.py', '--kit', expectedKitDir, '--out', 'out/practice', '--port', '8765', '--static', 'screen/dist',
        '--replay-url', replayBaseUrl],
      { cwd: appDir, stdio: 'inherit' },
    )
    backend.once('error', (error) => {
      spawnError = error
    })
    await waitForBackend(backend, () => spawnError)
  }

  if (backend && childStopped(backend)) throw new Error('Backend stopped immediately after becoming ready.')
  if (backend) {
    backend.once('exit', (code, signal) => {
      if (stopping) return
      const detail = code != null ? `exit code ${code}` : `signal ${signal}`
      process.stderr.write(`Backend stopped unexpectedly with ${detail}; stopping the frontend.\n`)
      process.exitCode = 1
      stop()
    })
  }
  if (replay) {
    replay.once('exit', (code, signal) => {
      if (stopping) return
      const detail = code != null ? `exit code ${code}` : `signal ${signal}`
      process.stderr.write(`Replay engine stopped unexpectedly with ${detail}; stopping the app.\n`)
      process.exitCode = 1
      stop()
    })
  }

  const viteEntry = resolve(screenDir, 'node_modules', 'vite', 'bin', 'vite.js')
  frontend = spawn(process.execPath, [viteEntry, '--host', '127.0.0.1'], {
    cwd: screenDir,
    env: configuredBaseUrl
      ? { ...process.env, VITE_API_BASE_URL: configuredBaseUrl }
      : process.env,
    stdio: 'inherit',
  })

  frontend.once('error', (error) => {
    if (stopping) return
    process.stderr.write(`Could not start the frontend: ${error.message}\n`)
    process.exitCode = 1
    stop()
  })

  frontend.once('exit', (code, signal) => {
    const alreadyStopping = stopping
    if (!alreadyStopping) stop()
    if (alreadyStopping) return
    if (code != null) process.exitCode = code
    else if (signal && signal !== 'SIGINT' && signal !== 'SIGTERM') process.exitCode = 1
  })
}

process.on('SIGINT', () => stop('SIGINT'))
process.on('SIGTERM', () => stop('SIGTERM'))
process.on('exit', () => stop())

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : error}\n`)
  process.exitCode = 1
  stop()
})
