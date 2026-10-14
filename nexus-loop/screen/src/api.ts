import type { DecisionRequest, ScreenModel } from './types'

const SCREEN_VERSION = 'nexus-loop-screen/1'
const configuredBase = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''

export class ApiError extends Error {
  status: number

  constructor(message: string, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function endpoint(path: string) {
  return `${configuredBase}/api${path}`
}

async function readJson(response: Response) {
  try {
    return await response.json()
  } catch {
    if (response.status >= 500) {
      throw new ApiError(
        'The frontend is running, but the Nexus Loop backend is unavailable. Start both with npm run dev.',
        response.status,
      )
    }
    throw new ApiError('The backend returned an unreadable response.', response.status)
  }
}

export async function loadScreen(signal?: AbortSignal): Promise<ScreenModel> {
  let response: Response
  try {
    response = await fetch(endpoint('/screen'), {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError('The Nexus Loop backend is not reachable. Check that the local server is running.')
  }

  const body = await readJson(response)
  if (!response.ok) {
    if (response.status === 404) {
      throw new ApiError('No analysis is available yet. Run the engine, then try again.', response.status)
    }
    throw new ApiError(body?.error || 'The analysis could not be loaded.', response.status)
  }
  if (body?.screen_version !== SCREEN_VERSION) {
    throw new ApiError('This analysis uses an incompatible screen format. Rebuild it with the current backend.')
  }
  if (!Array.isArray(body.findings) || !body.summary || !body.header) {
    throw new ApiError('The backend response is missing required screen data.')
  }
  return body as ScreenModel
}

export async function saveDecision(request: DecisionRequest): Promise<ScreenModel> {
  let response: Response
  try {
    response = await fetch(endpoint('/decisions'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(request),
    })
  } catch {
    throw new ApiError('Decision not saved. The backend is not reachable.')
  }

  const body = await readJson(response)
  if (!response.ok) {
    throw new ApiError(body?.error || 'Decision not saved.', response.status)
  }
  if (body?.screen?.screen_version !== SCREEN_VERSION) {
    throw new ApiError('Decision saved, but the refreshed screen could not be read.', response.status)
  }
  return body.screen as ScreenModel
}
