<script setup lang="ts">
import { useDark } from '@vueuse/core'
import {
  CalendarDays,
  ChartColumn,
  LogOut,
  Megaphone,
  Menu,
  MessageSquareQuote,
  Moon,
  Scissors,
  Settings,
  Sun,
  UserRound,
  Users,
  X,
} from 'lucide-vue-next'
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'

import { auth, logout } from '../api'
import { setAdminLocale } from '../i18n'

const { locale } = useI18n()
const router = useRouter()
const route = useRoute()
const dark = useDark({ storageKey: 'bb.admin-theme' })
const menuOpen = ref(false)

const links = [
  { to: '/journal', label: 'nav.journal', icon: CalendarDays },
  { to: '/dashboard', label: 'nav.dashboard', icon: ChartColumn },
  { to: '/clients', label: 'nav.clients', icon: Users },
  { to: '/masters', label: 'nav.masters', icon: UserRound },
  { to: '/services', label: 'nav.services', icon: Scissors },
  { to: '/broadcasts', label: 'nav.broadcasts', icon: Megaphone },
  { to: '/reviews', label: 'nav.reviews', icon: MessageSquareQuote },
  { to: '/settings', label: 'nav.settings', icon: Settings },
] as const

watch(
  () => route.fullPath,
  () => (menuOpen.value = false),
)

async function signOut(): Promise<void> {
  await logout()
  await router.replace('/login')
}
</script>

<template>
  <div class="min-h-dvh bg-bg lg:grid lg:grid-cols-[232px_1fr]">
    <header
      class="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-surface px-4 lg:hidden"
    >
      <button
        type="button"
        class="grid size-10 place-items-center rounded-lg hover:bg-surface-2"
        :aria-label="$t('nav.menu')"
        :aria-expanded="menuOpen"
        @click="menuOpen = !menuOpen"
      >
        <X v-if="menuOpen" :size="22" />
        <Menu v-else :size="22" />
      </button>
      <span class="font-sign text-xl font-bold">Brass &amp; Blade</span>
    </header>

    <aside
      class="fixed inset-y-0 left-0 z-40 flex w-[232px] flex-col border-r border-line bg-surface transition-transform lg:sticky lg:top-0 lg:h-dvh lg:translate-x-0"
      :class="menuOpen ? 'translate-x-0' : '-translate-x-full'"
    >
      <div class="flex items-center gap-2 px-5 pt-5 pb-6">
        <span class="pole block h-7 w-2.5 rounded-full" aria-hidden="true" />
        <span class="font-sign text-2xl leading-none font-bold">Brass &amp; Blade</span>
      </div>
      <nav class="flex-1 space-y-0.5 px-3" aria-label="Main">
        <RouterLink
          v-for="link in links"
          :key="link.to"
          :to="link.to"
          class="flex items-center gap-3 rounded-lg px-3 py-2 text-[15px] font-medium text-muted transition-colors hover:bg-surface-2 hover:text-ink"
          active-class="!bg-accent-soft !text-accent"
        >
          <component :is="link.icon" :size="18" :stroke-width="1.75" />
          {{ $t(link.label) }}
        </RouterLink>
      </nav>
      <div class="space-y-3 border-t border-line p-4">
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="grid size-9 place-items-center rounded-lg border border-line hover:bg-surface-2"
            :aria-label="$t('nav.theme')"
            @click="dark = !dark"
          >
            <Sun v-if="dark" :size="16" />
            <Moon v-else :size="16" />
          </button>
          <div
            class="flex rounded-lg border border-line p-0.5 text-xs font-semibold"
            role="radiogroup"
          >
            <button
              v-for="option in ['ru', 'en'] as const"
              :key="option"
              type="button"
              role="radio"
              :aria-checked="locale === option"
              class="rounded-md px-2 py-1 uppercase"
              :class="locale === option ? 'bg-ink text-bg' : 'text-muted'"
              @click="setAdminLocale(option)"
            >
              {{ option }}
            </button>
          </div>
        </div>
        <div class="flex items-center justify-between gap-2">
          <div class="min-w-0">
            <p class="truncate text-sm font-semibold">{{ auth.admin?.name }}</p>
            <p class="truncate text-xs text-faint">{{ auth.admin?.email }}</p>
          </div>
          <button
            type="button"
            class="grid size-9 shrink-0 place-items-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink"
            :aria-label="$t('nav.logout')"
            @click="signOut"
          >
            <LogOut :size="16" />
          </button>
        </div>
      </div>
    </aside>
    <div
      v-if="menuOpen"
      class="fixed inset-0 z-30 bg-black/40 lg:hidden"
      @click="menuOpen = false"
    />

    <div class="min-w-0">
      <p
        v-if="auth.admin?.demo"
        class="border-b border-line bg-brass-soft px-4 py-2 text-center text-xs font-medium text-brass sm:text-sm"
      >
        {{ $t('common.demoBanner') }}
      </p>
      <RouterView />
    </div>
  </div>
</template>
