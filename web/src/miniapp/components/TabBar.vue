<script setup lang="ts">
import { CalendarCheck, Scissors, UserRound } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'

const tabs = [
  { to: '/', label: 'nav.book', icon: Scissors },
  { to: '/bookings', label: 'nav.bookings', icon: CalendarCheck },
  { to: '/profile', label: 'nav.profile', icon: UserRound },
] as const
</script>

<template>
  <nav
    class="fixed inset-x-0 bottom-0 z-20 mx-auto grid max-w-[480px] grid-cols-3 border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur"
    aria-label="Main"
  >
    <RouterLink
      v-for="tab in tabs"
      :key="tab.to"
      :to="tab.to"
      class="flex flex-col items-center gap-0.5 py-2 text-[11px] font-semibold text-faint"
      exact-active-class="!text-accent"
    >
      <component :is="tab.icon" :size="22" :stroke-width="1.75" />
      {{ $t(tab.label) }}
    </RouterLink>
  </nav>
</template>
