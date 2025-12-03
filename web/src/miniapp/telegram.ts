/** The slice of Telegram.WebApp this app uses, plus a browser fallback for the demo. */

type Haptic = 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'
type Notice = 'error' | 'success' | 'warning'
type InvoiceStatus = 'paid' | 'cancelled' | 'failed' | 'pending'

interface BottomButton {
  setParams(params: {
    text?: string
    color?: string
    text_color?: string
    is_active?: boolean
    is_visible?: boolean
  }): void
  show(): void
  hide(): void
  showProgress(leaveActive?: boolean): void
  hideProgress(): void
  onClick(cb: () => void): void
  offClick(cb: () => void): void
}

interface Inset {
  top: number
  bottom: number
  left: number
  right: number
}

interface WebApp {
  initData: string
  initDataUnsafe: { start_param?: string; user?: { language_code?: string } }
  platform: string
  version: string
  colorScheme: 'light' | 'dark'
  isFullscreen?: boolean
  safeAreaInset?: Inset
  contentSafeAreaInset?: Inset
  ready(): void
  expand(): void
  requestFullscreen?(): void
  disableVerticalSwipes?(): void
  isVersionAtLeast(version: string): boolean
  setHeaderColor(color: string): void
  setBackgroundColor(color: string): void
  setBottomBarColor?(color: string): void
  onEvent(event: string, cb: () => void): void
  openInvoice(url: string, cb: (status: InvoiceStatus) => void): void
  openTelegramLink(url: string): void
  openLink(url: string): void
  MainButton: BottomButton
  BackButton: {
    show(): void
    hide(): void
    onClick(cb: () => void): void
    offClick(cb: () => void): void
  }
  HapticFeedback: {
    impactOccurred(style: Haptic): void
    selectionChanged(): void
    notificationOccurred(type: Notice): void
  }
}

declare global {
  interface Window {
    Telegram?: { WebApp?: WebApp }
  }
}

export const webApp: WebApp | undefined =
  window.Telegram?.WebApp && window.Telegram.WebApp.initData ? window.Telegram.WebApp : undefined

export const inTelegram = webApp !== undefined

export function startParam(): string | undefined {
  return webApp?.initDataUnsafe.start_param
}

export function haptic(kind: 'select' | Haptic | Notice = 'select'): void {
  if (!webApp?.isVersionAtLeast('6.1')) return
  if (kind === 'select') webApp.HapticFeedback.selectionChanged()
  else if (kind === 'error' || kind === 'success' || kind === 'warning')
    webApp.HapticFeedback.notificationOccurred(kind)
  else webApp.HapticFeedback.impactOccurred(kind)
}

export function applyChrome(dark: boolean, colors: { bg: string; surface: string }): void {
  if (!webApp) return
  if (webApp.isVersionAtLeast('6.1')) {
    webApp.setHeaderColor(colors.bg)
    webApp.setBackgroundColor(colors.bg)
  }
  if (webApp.isVersionAtLeast('7.10')) webApp.setBottomBarColor?.(colors.surface)
  document.documentElement.classList.toggle('dark', dark)
}

/** Fullscreen only on phones: on desktop it would stretch Telegram over the whole monitor. */
export function goFullscreen(): void {
  if (!webApp) return
  webApp.expand()
  if (['ios', 'android'].includes(webApp.platform) && webApp.isVersionAtLeast('8.0')) {
    webApp.requestFullscreen?.()
  }
  if (webApp.isVersionAtLeast('7.7')) webApp.disableVerticalSwipes?.()
}

/** Top padding that keeps content clear of Telegram's floating Close and menu buttons. */
export function topInset(): number {
  if (!webApp?.isFullscreen) return 0
  return (webApp.safeAreaInset?.top ?? 0) + (webApp.contentSafeAreaInset?.top ?? 0)
}

export function openInvoice(url: string): Promise<InvoiceStatus> {
  return new Promise((resolve) => {
    if (!webApp) return resolve('failed')
    webApp.openInvoice(url, resolve)
  })
}

export function share(url: string, text: string): void {
  // encodeURIComponent, not URLSearchParams: Telegram does not decode "+" back into spaces.
  const link = `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`
  if (webApp) webApp.openTelegramLink(link)
  else window.open(link, '_blank', 'noopener')
}
