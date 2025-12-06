import { reactive } from 'vue'

import { createApi, type Schemas } from '@/shared/api/client'

export const auth = reactive({
  checked: false,
  admin: null as Schemas['AdminOut'] | null,
})

export const api = createApi({
  credentials: 'include',
  onUnauthorized: () => {
    auth.admin = null
  },
})

export async function loadAdmin(): Promise<void> {
  try {
    auth.admin = await api.get<Schemas['AdminOut']>('/api/admin/auth/me')
  } catch {
    auth.admin = null
  } finally {
    auth.checked = true
  }
}

export async function demoLogin(): Promise<void> {
  auth.admin = await api.post<Schemas['AdminOut']>('/api/admin/auth/demo')
}

export async function passwordLogin(email: string, password: string): Promise<void> {
  auth.admin = await api.post<Schemas['AdminOut']>('/api/admin/auth/login', { email, password })
}

export async function logout(): Promise<void> {
  await api.post('/api/admin/auth/logout')
  auth.admin = null
}

export function downloadUrl(path: string, query: Record<string, string | number>): string {
  const url = new URL(path, window.location.origin)
  for (const [key, value] of Object.entries(query)) url.searchParams.set(key, String(value))
  return url.toString()
}
