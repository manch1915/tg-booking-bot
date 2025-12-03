import type { components } from './schema'

export type Schemas = components['schemas']

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: Record<string, unknown> = {},
  ) {
    super(message)
  }
}

type Query = Record<string, string | number | boolean | null | undefined>

interface ClientOptions {
  token?: () => string | null
  credentials?: RequestCredentials
  onUnauthorized?: () => void
}

export function createApi(options: ClientOptions = {}) {
  async function request<T>(method: string, path: string, body?: unknown, query?: Query) {
    const url = new URL(path, window.location.origin)
    for (const [key, value] of Object.entries(query ?? {})) {
      if (value !== null && value !== undefined && value !== '')
        url.searchParams.set(key, String(value))
    }
    const headers: Record<string, string> = { Accept: 'application/json' }
    const token = options.token?.()
    if (token) headers.Authorization = `Bearer ${token}`
    if (body !== undefined) headers['Content-Type'] = 'application/json'

    const response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: options.credentials ?? 'same-origin',
    })
    if (response.status === 204) return undefined as T
    const data: unknown = await response.json().catch(() => null)
    if (!response.ok) {
      const error = (data ?? {}) as {
        error?: string
        message?: string
        details?: Record<string, unknown>
      }
      if (response.status === 401) options.onUnauthorized?.()
      throw new ApiError(
        response.status,
        error.error ?? 'http_error',
        error.message ?? response.statusText,
        error.details,
      )
    }
    return data as T
  }

  return {
    get: <T>(path: string, query?: Query) => request<T>('GET', path, undefined, query),
    post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
    put: <T>(path: string, body: unknown) => request<T>('PUT', path, body),
    patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
    del: <T>(path: string) => request<T>('DELETE', path),
  }
}

export type Api = ReturnType<typeof createApi>
