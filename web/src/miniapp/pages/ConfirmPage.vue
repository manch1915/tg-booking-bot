<script setup lang="ts">
import { useQueryClient } from '@tanstack/vue-query'
import { CreditCard, Star } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { ApiError, type Schemas } from '@/shared/api/client'
import { dateTime, money } from '@/shared/format'
import { photo } from '@/shared/photo'

import Avatar from '../components/Avatar.vue'
import PageHeader from '../components/PageHeader.vue'
import { useMainAction } from '../composables/mainAction'
import { draft } from '../draft'
import { rememberIntent } from '../payments'
import { useCatalog, useOffers } from '../queries'
import { api, locale, refreshClient, session } from '../session'
import { haptic } from '../telegram'

const router = useRouter()
const { t } = useI18n()
const queryClient = useQueryClient()
const lang = computed(() => locale())
const business = computed(() => session.business!)
const tz = computed(() => business.value.timezone)

if (draft.serviceId === null || draft.startsAt === null) void router.replace('/')

const catalog = useCatalog()
const offers = useOffers(() => draft.serviceId)
const submitting = ref(false)
const error = ref('')

const service = computed(() =>
  catalog.data.value?.categories.flatMap((c) => c.services).find((s) => s.id === draft.serviceId),
)
const candidates = computed(() =>
  (offers.data.value ?? []).filter((o) =>
    draft.masterId !== null
      ? o.master.id === draft.masterId
      : draft.slotMasters.includes(o.master.id),
  ),
)
const master = computed(() => (candidates.value.length === 1 ? candidates.value[0] : undefined))
const prices = computed(() => candidates.value.map((o) => o.price))
const price = computed(() => Math.max(0, ...prices.value))
const priceLabel = computed(() => {
  const low = Math.min(...prices.value)
  const high = Math.max(...prices.value)
  return low === high ? fmt(low) : `${fmt(low)}–${fmt(high)}`
})

const bonusAvailable = computed(() => {
  const share = Math.floor((price.value * business.value.max_bonus_share_percent + 50) / 100)
  return Math.max(0, Math.min(session.client?.bonus_balance ?? 0, share))
})
const bonus = computed(() => (draft.useBonus ? bonusAvailable.value : 0))
const deposit = computed(() => {
  const raw = Math.floor((price.value * business.value.deposit_percent + 50) / 100)
  const rounded = raw ? Math.ceil(raw / 100) * 100 : 0
  return Math.min(rounded, price.value - bonus.value)
})
const stars = computed(
  () =>
    business.value.stars_fixed_price ??
    Math.max(1, Math.ceil((deposit.value * business.value.stars_per_usd) / 100)),
)
const deadline = computed(() => {
  if (!draft.startsAt) return ''
  const moment = new Date(draft.startsAt).getTime() - business.value.cancel_window_hours * 3_600_000
  return dateTime(new Date(moment).toISOString(), lang.value, tz.value)
})
const payLabel = computed(() =>
  draft.method === 'stars' ? `${stars.value} ★` : fmt(deposit.value),
)

function fmt(cents: number): string {
  return money(cents, business.value.currency, lang.value)
}

function toggleBonus(): void {
  haptic()
  draft.useBonus = !draft.useBonus
}

function pick(method: Schemas['PaymentMethod']): void {
  haptic()
  draft.method = method
}

async function submit(): Promise<void> {
  submitting.value = true
  error.value = ''
  try {
    const created = await api.post<Schemas['BookingCreatedOut']>('/api/app/bookings', {
      service_id: draft.serviceId,
      master_id: draft.masterId,
      starts_at: draft.startsAt,
      payment_method: deposit.value ? draft.method : 'on_site',
      use_bonus: draft.useBonus,
      comment: draft.comment,
    })
    await queryClient.invalidateQueries({ queryKey: ['bookings'] })
    void refreshClient()
    haptic('success')
    const id = created.booking.id
    if (created.payment) {
      rememberIntent(id, created.payment)
      void router.replace({ name: 'pay', params: { id } })
    } else {
      void router.replace({ name: 'done', params: { id } })
    }
  } catch (e) {
    haptic('error')
    if (e instanceof ApiError && e.status === 409) {
      error.value = t('confirm.slotTaken')
      await queryClient.invalidateQueries({ queryKey: ['slots'] })
    } else {
      error.value = e instanceof Error ? e.message : String(e)
    }
  } finally {
    submitting.value = false
  }
}

useMainAction(
  () => ({
    text: deposit.value ? t('confirm.pay', { amount: payLabel.value }) : t('confirm.book'),
    disabled: !candidates.value.length,
    loading: submitting.value,
  }),
  () => void submit(),
)
</script>

<template>
  <main>
    <PageHeader :title="$t('confirm.title')" back="/time" />

    <section
      v-if="service && draft.startsAt"
      class="mx-4 mt-2 overflow-hidden rounded-[20px] bg-surface"
    >
      <div class="flex gap-3 p-4">
        <img
          :src="photo(service.photo_url, 64)"
          alt=""
          class="size-16 rounded-xl bg-surface-2 object-cover"
        />
        <div class="min-w-0">
          <p class="font-semibold">{{ service.name[lang] }}</p>
          <p class="font-sign text-2xl leading-tight font-semibold num">
            {{ dateTime(draft.startsAt, lang, tz) }}
          </p>
        </div>
      </div>
      <div class="flex items-center gap-3 border-t border-line px-4 py-3">
        <Avatar
          v-if="master"
          :src="master.master.photo_url"
          :name="master.master.name[lang]"
          :color="master.master.color"
          :size="32"
        />
        <span class="flex-1 text-sm">
          {{ master ? master.master.name[lang] : $t('common.anyMasterHint') }}
        </span>
      </div>
      <dl class="space-y-2 border-t border-line px-4 py-3 text-sm">
        <div class="flex justify-between">
          <dt class="text-muted">{{ $t('confirm.price') }}</dt>
          <dd class="font-semibold num">{{ priceLabel }}</dd>
        </div>
        <div v-if="bonus" class="flex justify-between text-brass">
          <dt>{{ $t('confirm.bonus') }}</dt>
          <dd class="font-semibold num">−{{ fmt(bonus) }}</dd>
        </div>
        <div v-if="deposit" class="flex justify-between">
          <dt class="text-muted">{{ $t('confirm.deposit') }}</dt>
          <dd class="font-semibold num">{{ fmt(deposit) }}</dd>
        </div>
        <div v-if="deposit" class="flex justify-between">
          <dt class="text-muted">{{ $t('confirm.rest') }}</dt>
          <dd class="num">{{ fmt(price - bonus - deposit) }}</dd>
        </div>
      </dl>
    </section>

    <button
      v-if="bonusAvailable"
      type="button"
      role="switch"
      :aria-checked="draft.useBonus"
      class="mx-4 mt-3 flex w-[calc(100%-2rem)] items-center gap-3 rounded-[18px] bg-surface p-4 text-left"
      @click="toggleBonus"
    >
      <span class="flex-1">
        <span class="block font-semibold">{{ $t('confirm.bonus') }}</span>
        <span class="text-sm text-muted">
          {{
            $t('confirm.bonusHint', {
              amount: fmt(bonusAvailable),
              share: business.max_bonus_share_percent,
            })
          }}
        </span>
      </span>
      <span
        class="relative h-7 w-12 rounded-full transition-colors"
        :class="draft.useBonus ? 'bg-brass' : 'bg-line'"
        aria-hidden="true"
      >
        <span
          class="absolute top-1 left-1 size-5 rounded-full bg-white shadow transition-transform"
          :class="draft.useBonus ? 'translate-x-5' : ''"
        />
      </span>
    </button>

    <section v-if="deposit" class="px-4 pt-5" aria-labelledby="method">
      <h2 id="method" class="pb-2 font-sign text-xl font-semibold">{{ $t('confirm.method') }}</h2>
      <div class="grid grid-cols-2 gap-2" role="radiogroup">
        <button
          type="button"
          role="radio"
          :aria-checked="draft.method === 'card'"
          class="rounded-[16px] border-2 p-3 text-left transition-colors"
          :class="
            draft.method === 'card'
              ? 'border-accent bg-accent-soft'
              : 'border-transparent bg-surface'
          "
          @click="pick('card')"
        >
          <CreditCard :size="20" :stroke-width="1.75" class="text-accent" />
          <span class="mt-2 block font-semibold">{{ $t('confirm.card') }}</span>
          <span class="font-sign text-lg font-semibold num">{{ fmt(deposit) }}</span>
        </button>
        <button
          v-if="business.stars_enabled"
          type="button"
          role="radio"
          :aria-checked="draft.method === 'stars'"
          class="rounded-[16px] border-2 p-3 text-left transition-colors"
          :class="
            draft.method === 'stars'
              ? 'border-brass bg-brass-soft'
              : 'border-transparent bg-surface'
          "
          @click="pick('stars')"
        >
          <Star :size="20" :stroke-width="1.75" class="fill-brass text-brass" />
          <span class="mt-2 block font-semibold">{{ $t('confirm.stars') }}</span>
          <span class="font-sign text-lg font-semibold num">{{ stars }} ★</span>
        </button>
      </div>
    </section>

    <section class="px-4 pt-5">
      <label for="comment" class="pb-2 font-sign text-xl font-semibold">{{
        $t('confirm.comment')
      }}</label>
      <textarea
        id="comment"
        v-model="draft.comment"
        rows="2"
        maxlength="500"
        :placeholder="$t('confirm.commentPlaceholder')"
        class="mt-2 w-full resize-none rounded-[16px] border border-line bg-surface p-3 text-[15px] placeholder:text-faint focus:border-accent focus:outline-none"
      />
    </section>

    <p class="px-4 pt-3 text-sm leading-snug text-muted">{{ $t('confirm.rules', { deadline }) }}</p>
    <p
      v-if="error"
      class="mx-4 mt-3 rounded-xl bg-danger-soft p-3 text-sm text-danger"
      role="alert"
    >
      {{ error }}
    </p>
  </main>
</template>
