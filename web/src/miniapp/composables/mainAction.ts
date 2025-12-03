import { onBeforeUnmount, reactive, watch, watchEffect } from 'vue'

import { inTelegram, webApp } from '../telegram'

interface ActionState {
  text: string
  visible: boolean
  disabled: boolean
  loading: boolean
}

export const mainAction = reactive<ActionState & { handler: (() => void) | null }>({
  text: '',
  visible: false,
  disabled: false,
  loading: false,
  handler: null,
})

function readCssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

if (inTelegram && webApp) {
  const button = webApp.MainButton
  button.onClick(() => {
    if (!mainAction.disabled && !mainAction.loading) mainAction.handler?.()
  })
  watch(
    () => ({ ...mainAction }),
    (state) => {
      button.setParams({
        text: state.text,
        color: readCssVar(state.disabled ? '--line' : '--accent'),
        text_color: readCssVar(state.disabled ? '--muted' : '--accent-ink'),
        is_active: !state.disabled,
        is_visible: state.visible,
      })
      if (state.loading) button.showProgress(false)
      else button.hideProgress()
    },
    { deep: true },
  )
}

/**
 * Drives Telegram's MainButton inside Telegram and the in-page bottom button in a browser.
 * The getter is reactive, so the label can follow the current selection.
 */
export function useMainAction(state: () => Partial<ActionState>, handler: () => void): void {
  const stop = watchEffect(() => {
    const next = state()
    mainAction.text = next.text ?? ''
    mainAction.visible = next.visible ?? true
    mainAction.disabled = next.disabled ?? false
    mainAction.loading = next.loading ?? false
    mainAction.handler = handler
  })
  onBeforeUnmount(() => {
    stop()
    if (mainAction.handler === handler) {
      mainAction.visible = false
      mainAction.handler = null
    }
  })
}
