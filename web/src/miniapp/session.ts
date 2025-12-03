import { reactive } from 'vue'

import { createApi, type Schemas } from '@/shared/api/client'
import type { Locale } from '@/shared/format'

import { i18n } from './i18n'
import { inTelegram, webApp } from './telegram'

const TOKEN_KEY = 'bb.client-token'

export const session = reactive({
  ready: false,
  failed: false,
  token: null as string | null,
  client: null as Schemas['ClientOut'] | null,
  business: null as Schemas['BusinessOut'] | null,
})

function stored(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

function remember(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token)
  } catch {
    // Private mode: the session simply lasts until the tab closes.
  }
}

export const api = createApi({ token: () => session.token })

export function setLocale(locale: Locale): void {
  i18n.global.locale.value = locale
  document.documentElement.lang = locale
}

export function locale(): Locale {
  return i18n.global.locale.value
}

async function signIn(): Promise<Schemas['AuthOut']> {
  if (inTelegram && webApp) {
    return api.post<Schemas['AuthOut']>('/api/app/auth/telegram', { init_data: webApp.initData })
  }
  const saved = stored()
  if (saved) {
    session.token = saved
    try {
      const client = await api.get<Schemas['ClientOut']>('/api/app/me')
      return { token: saved, client }
    } catch {
      session.token = null
    }
  }
  const language = navigator.language.startsWith('ru') ? 'ru' : 'en'
  return api.post<Schemas['AuthOut']>('/api/app/auth/demo', { language })
}

export async function startSession(): Promise<void> {
  session.failed = false
  try {
    const [auth, business] = await Promise.all([
      signIn(),
      api.get<Schemas['BusinessOut']>('/api/app/business'),
    ])
    session.token = auth.token
    session.client = auth.client
    session.business = business
    if (!inTelegram) remember(auth.token)
    setLocale(auth.client.language)
    session.ready = true
  } catch {
    session.failed = true
  }
}

export async function refreshClient(): Promise<void> {
  session.client = await api.get<Schemas['ClientOut']>('/api/app/me')
}
