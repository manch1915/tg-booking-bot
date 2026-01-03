<script setup lang="ts">
import { usePreferredDark } from '@vueuse/core'
import { computed, onMounted, ref, watchEffect } from 'vue'
import { RouterView, useRoute } from 'vue-router'

import BottomAction from './components/BottomAction.vue'
import TabBar from './components/TabBar.vue'
import { mainAction } from './composables/mainAction'
import { session, startSession } from './session'
import { applyChrome, goFullscreen, inTelegram, topInset, webApp } from './telegram'

const LIGHT = { bg: '#eef0ec', surface: '#ffffff' }
const DARK = { bg: '#0f1714', surface: '#18221e' }

const route = useRoute()
const prefersDark = usePreferredDark()
const telegramScheme = ref(webApp?.colorScheme)
const dark = computed(() => (inTelegram ? telegramScheme.value === 'dark' : prefersDark.value))
const inset = ref(topInset())
const topLevel = computed(() => ['home', 'bookings', 'profile'].includes(String(route.name)))
// Browsing the catalogue needs no account, so only these screens wait for sign-in.
const publicScreen = computed(() => ['home', 'service', 'time'].includes(String(route.name)))
const loading = computed(() => !session.business || (!publicScreen.value && !session.ready))

watchEffect(() => {
  document.documentElement.classList.toggle('dark', dark.value)
  applyChrome(dark.value, dark.value ? DARK : LIGHT)
})

onMounted(() => {
  webApp?.ready()
  goFullscreen()
  const syncInset = () => (inset.value = topInset())
  webApp?.onEvent('themeChanged', () => (telegramScheme.value = webApp?.colorScheme))
  webApp?.onEvent('fullscreenChanged', syncInset)
  webApp?.onEvent('safeAreaChanged', syncInset)
  webApp?.onEvent('contentSafeAreaChanged', syncInset)
  void startSession()
})
</script>

<template>
  <div
    class="mx-auto min-h-dvh max-w-[480px] bg-bg"
    :class="topLevel || (!inTelegram && mainAction.visible) ? 'pb-24' : 'pb-6'"
    :style="{ paddingTop: `${inset}px` }"
  >
    <div v-if="session.failed" class="grid min-h-dvh place-items-center p-8 text-center">
      <div>
        <p class="text-muted">{{ $t('common.loadError') }}</p>
        <button
          type="button"
          class="mt-4 rounded-full bg-accent px-5 py-2.5 font-semibold text-accent-ink"
          @click="startSession"
        >
          {{ $t('common.retry') }}
        </button>
      </div>
    </div>
    <div v-else-if="loading" class="grid min-h-dvh place-items-center" aria-busy="true">
      <span class="pole block h-2 w-24 overflow-hidden rounded-full" aria-hidden="true" />
    </div>
    <template v-else>
      <RouterView v-slot="{ Component }">
        <Transition
          mode="out-in"
          enter-from-class="opacity-0"
          leave-to-class="opacity-0"
          enter-active-class="transition-opacity duration-150"
          leave-active-class="transition-opacity duration-100"
        >
          <component :is="Component" />
        </Transition>
      </RouterView>
      <TabBar v-if="topLevel && !mainAction.visible" />
      <BottomAction v-if="!inTelegram" />
    </template>
  </div>
</template>
