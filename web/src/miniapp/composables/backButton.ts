import { onBeforeUnmount, onMounted } from 'vue'

import { inTelegram, webApp } from '../telegram'

/** Shows Telegram's native back button while the page is open. */
export function useTelegramBack(onBack: () => void): void {
  if (!inTelegram || !webApp) return
  const back = webApp.BackButton
  onMounted(() => {
    back.onClick(onBack)
    back.show()
  })
  onBeforeUnmount(() => {
    back.offClick(onBack)
    back.hide()
  })
}
