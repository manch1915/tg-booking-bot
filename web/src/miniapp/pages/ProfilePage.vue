<script setup lang="ts">
import { useClipboard } from '@vueuse/core'
import { Copy, Send } from 'lucide-vue-next'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { day, money, type Locale } from '@/shared/format'

import LoadState from '../components/LoadState.vue'
import PageHeader from '../components/PageHeader.vue'
import { useBonusHistory } from '../queries'
import { api, locale, session, setLocale } from '../session'
import { haptic, share } from '../telegram'

const { t } = useI18n()
const history = useBonusHistory()
const { copy, copied } = useClipboard()
const lang = computed(() => locale())
const business = computed(() => session.business!)
const client = computed(() => session.client!)

function fmt(cents: number): string {
  return money(cents, business.value.currency, lang.value)
}

function invite(): void {
  haptic('light')
  share(client.value.referral_link, t('profile.shareText', { name: business.value.name }))
}

async function switchLanguage(next: Locale): Promise<void> {
  haptic()
  setLocale(next)
  session.client = await api.patch('/api/app/me', { language: next })
}
</script>

<template>
  <main>
    <PageHeader :title="client.name" />

    <section
      class="relative mx-4 mt-2 overflow-hidden rounded-[22px] bg-leather p-5 text-leather-ink"
    >
      <p class="text-sm opacity-70">{{ $t('profile.balance') }}</p>
      <p class="mt-1 font-sign text-[52px] leading-none font-bold text-leather-brass num">
        {{ fmt(client.bonus_balance) }}
      </p>
      <p class="mt-2 text-sm opacity-80">
        {{ $t('profile.balanceHint', { cashback: business.cashback_percent }) }}
      </p>
      <p class="mt-3 flex gap-4 text-xs font-semibold opacity-70">
        <span>{{ $t('profile.visits', { n: client.visits }) }}</span>
        <span>{{ $t('profile.invited', { n: client.invited }) }}</span>
      </p>
    </section>

    <section class="mx-4 mt-3 rounded-[20px] bg-surface p-4">
      <h2 class="font-sign text-xl font-semibold">{{ $t('profile.invite') }}</h2>
      <p class="mt-1 text-sm text-muted">
        {{
          $t('profile.inviteText', {
            welcome: fmt(business.welcome_bonus),
            referral: fmt(business.referral_bonus),
          })
        }}
      </p>
      <div class="mt-3 flex gap-2">
        <button
          type="button"
          class="flex flex-1 items-center justify-center gap-2 rounded-[12px] bg-accent py-2.5 text-sm font-semibold text-accent-ink"
          @click="invite"
        >
          <Send :size="16" /> {{ $t('profile.share') }}
        </button>
        <button
          type="button"
          class="flex items-center gap-2 rounded-[12px] bg-surface-2 px-3 text-sm font-semibold"
          @click="copy(client.referral_link)"
        >
          <Copy :size="16" /> {{ copied ? $t('profile.copied') : $t('profile.copy') }}
        </button>
      </div>
    </section>

    <section class="mx-4 mt-3 flex items-center justify-between rounded-[20px] bg-surface p-4">
      <span class="font-semibold">{{ $t('profile.language') }}</span>
      <div
        class="flex rounded-full bg-surface-2 p-1"
        role="radiogroup"
        :aria-label="$t('profile.language')"
      >
        <button
          v-for="option in ['ru', 'en'] as const"
          :key="option"
          type="button"
          role="radio"
          :aria-checked="lang === option"
          class="rounded-full px-3 py-1 text-sm font-semibold uppercase"
          :class="lang === option ? 'bg-ink text-bg' : 'text-muted'"
          @click="switchLanguage(option)"
        >
          {{ option }}
        </button>
      </div>
    </section>

    <section class="px-4 pt-5">
      <h2 class="pb-2 font-sign text-xl font-semibold">{{ $t('profile.history') }}</h2>
      <LoadState
        :loading="history.isPending.value"
        :error="history.isError.value"
        :lines="2"
        @retry="history.refetch()"
      />
      <ul v-if="history.data.value" class="divide-y divide-line rounded-[18px] bg-surface">
        <li
          v-for="tx in history.data.value"
          :key="tx.id"
          class="flex items-center justify-between gap-3 px-4 py-3"
        >
          <span>
            <span class="block text-sm font-semibold">{{ $t(`profile.kinds.${tx.kind}`) }}</span>
            <span class="text-xs text-faint">{{
              day(tx.created_at, lang, business.timezone)
            }}</span>
          </span>
          <span
            class="font-sign text-lg font-semibold num"
            :class="tx.amount > 0 ? 'text-accent' : 'text-muted'"
          >
            {{ tx.amount > 0 ? '+' : '' }}{{ fmt(tx.amount) }}
          </span>
        </li>
      </ul>
    </section>
  </main>
</template>
