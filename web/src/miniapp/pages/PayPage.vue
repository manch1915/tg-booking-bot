<script setup lang="ts">
import { useQueryClient } from '@tanstack/vue-query'
import { ShieldCheck } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import type { Schemas } from '@/shared/api/client'
import { dateTime, money } from '@/shared/format'

import HoldTimer from '../components/HoldTimer.vue'
import PageHeader from '../components/PageHeader.vue'
import { useMainAction } from '../composables/mainAction'
import { forgetIntent, intentFor } from '../payments'
import { api, locale, refreshClient, session } from '../session'
import { haptic, openInvoice } from '../telegram'

const props = defineProps<{ id: number }>()
const router = useRouter()
const { t } = useI18n()
const queryClient = useQueryClient()
const lang = computed(() => locale())
const tz = computed(() => session.business!.timezone)

const booking = ref<Schemas['BookingOut'] | null>(null)
const intent = ref<Schemas['PaymentIntentOut'] | null>(null)
const busy = ref(false)
const notice = ref('')
const expired = ref(false)

const amount = computed(() =>
  intent.value ? money(intent.value.amount, intent.value.currency, lang.value) : '',
)
const isDemo = computed(() => intent.value?.provider === 'demo')

async function load(): Promise<void> {
  booking.value = await api.get<Schemas['BookingOut']>(`/api/app/bookings/${props.id}`)
  if (booking.value.status !== 'pending_payment') return finish()
  intent.value = await intentFor(props.id)
}

async function finish(): Promise<void> {
  forgetIntent(props.id)
  await queryClient.invalidateQueries({ queryKey: ['bookings'] })
  void refreshClient()
  void router.replace({ name: 'done', params: { id: props.id } })
}

/** Telegram reports "paid" before our bot has processed the payment, so wait for it. */
async function waitForConfirmation(): Promise<void> {
  for (let attempt = 0; attempt < 15; attempt++) {
    const fresh = await api.get<Schemas['BookingOut']>(`/api/app/bookings/${props.id}`)
    if (fresh.status === 'confirmed') return finish()
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }
  notice.value = t('common.loadError')
}

async function pay(): Promise<void> {
  if (!intent.value || expired.value) return
  busy.value = true
  notice.value = ''
  try {
    if (isDemo.value) {
      await api.post(`/api/app/payments/${intent.value.payment_id}/demo-confirm`)
      haptic('success')
      return await finish()
    }
    const status = await openInvoice(intent.value.invoice_url ?? '')
    if (status === 'paid') {
      haptic('success')
      await waitForConfirmation()
    } else {
      notice.value = t('pay.cancelled')
    }
  } catch (e) {
    haptic('error')
    notice.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}

function onExpired(): void {
  expired.value = true
  notice.value = t('pay.expired')
  void queryClient.invalidateQueries({ queryKey: ['bookings'] })
}

useMainAction(
  () => ({
    text: expired.value ? t('slots.pickTime') : t('pay.demoPay', { amount: amount.value }),
    visible: !!intent.value,
    loading: busy.value,
  }),
  () => {
    if (expired.value) void router.replace({ name: 'time' })
    else void pay()
  },
)

onMounted(async () => {
  await load()
  // Inside Telegram the invoice opens right away; the button stays as a retry.
  if (intent.value && !isDemo.value) void pay()
})
</script>

<template>
  <main>
    <PageHeader :title="$t('pay.title')" back="/bookings" />
    <div v-if="booking" class="space-y-3 px-4 pt-2">
      <HoldTimer
        v-if="booking.hold_expires_at && !expired"
        :until="booking.hold_expires_at"
        :total="session.business!.hold_minutes"
        @expired="onExpired"
      />
      <section class="rounded-[18px] bg-surface p-4">
        <p class="font-semibold">{{ booking.service.name[lang] }}</p>
        <p class="font-sign text-2xl font-semibold num">
          {{ dateTime(booking.starts_at, lang, tz) }}
        </p>
        <p class="text-sm text-muted">{{ booking.master.name[lang] }}</p>
      </section>
      <section v-if="isDemo" class="flex gap-3 rounded-[18px] bg-brass-soft p-4">
        <ShieldCheck :size="22" class="shrink-0 text-brass" />
        <div>
          <p class="font-semibold">{{ $t('pay.demoTitle') }}</p>
          <p class="mt-1 text-sm text-ink/80">{{ $t('pay.demoText') }}</p>
        </div>
      </section>
      <p v-if="notice" class="rounded-xl bg-danger-soft p-3 text-sm text-danger" role="alert">
        {{ notice }}
      </p>
    </div>
  </main>
</template>
