<script setup lang="ts">
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { Check } from 'lucide-vue-next'
import { ref, watch } from 'vue'

import { api } from '../api'
import { useBusiness } from '../context'

const queryClient = useQueryClient()
const business = useBusiness()
const saved = ref(false)

const form = ref({
  name: '',
  tagline_ru: '',
  tagline_en: '',
  address: '',
  phone: '',
  cancel_window_hours: 3,
  deposit_percent: 30,
  cashback_percent: 5,
  max_bonus_share_percent: 30,
  referral_bonus: 5,
  welcome_bonus: 3,
  hold_minutes: 10,
  stars_enabled: true,
})

watch(
  () => business.data.value,
  (b) => {
    if (!b) return
    form.value = {
      name: b.name,
      tagline_ru: b.tagline.ru,
      tagline_en: b.tagline.en,
      address: b.address,
      phone: b.phone,
      cancel_window_hours: b.cancel_window_hours,
      deposit_percent: b.deposit_percent,
      cashback_percent: b.cashback_percent,
      max_bonus_share_percent: b.max_bonus_share_percent,
      referral_bonus: b.referral_bonus / 100,
      welcome_bonus: b.welcome_bonus / 100,
      hold_minutes: b.hold_minutes,
      stars_enabled: b.stars_enabled,
    }
  },
  { immediate: true },
)

const save = useMutation({
  mutationFn: () =>
    api.put('/api/admin/settings', {
      ...form.value,
      referral_bonus: Math.round(form.value.referral_bonus * 100),
      welcome_bonus: Math.round(form.value.welcome_bonus * 100),
    }),
  onSuccess: async () => {
    saved.value = true
    setTimeout(() => (saved.value = false), 2000)
    await queryClient.invalidateQueries({ queryKey: ['admin', 'settings'] })
  },
})

const numberFields = [
  ['cancel_window_hours', 'settings.cancelWindow', 0, 72, 1],
  ['deposit_percent', 'settings.deposit', 0, 100, 5],
  ['cashback_percent', 'settings.cashback', 0, 50, 1],
  ['max_bonus_share_percent', 'settings.maxBonus', 0, 100, 5],
  ['referral_bonus', 'settings.referral', 0, 100, 0.5],
  ['welcome_bonus', 'settings.welcome', 0, 100, 0.5],
  ['hold_minutes', 'settings.hold', 3, 60, 1],
] as const
</script>

<template>
  <main class="p-4 lg:p-6">
    <h1 class="font-sign text-3xl font-semibold">{{ $t('nav.settings') }}</h1>
    <form class="mt-4 grid max-w-4xl gap-5 lg:grid-cols-2" @submit.prevent="save.mutate()">
      <fieldset class="space-y-3 rounded-2xl border border-line bg-surface p-4">
        <legend class="px-1 font-semibold">{{ $t('settings.business') }}</legend>
        <label
          v-for="key in ['name', 'tagline_ru', 'tagline_en', 'address', 'phone'] as const"
          :key="key"
          class="block"
        >
          <span class="text-sm text-muted">{{
            $t(
              `settings.${key === 'tagline_ru' ? 'taglineRu' : key === 'tagline_en' ? 'taglineEn' : key}`,
            )
          }}</span>
          <input
            v-model="form[key]"
            class="mt-1 h-10 w-full rounded-lg border border-line bg-surface px-3"
          />
        </label>
      </fieldset>
      <fieldset class="space-y-3 rounded-2xl border border-line bg-surface p-4">
        <legend class="px-1 font-semibold">{{ $t('settings.rules') }}</legend>
        <label
          v-for="[key, label, min, max, step] in numberFields"
          :key="key"
          class="flex items-center justify-between gap-3"
        >
          <span class="text-sm">{{ $t(label) }}</span>
          <input
            v-model.number="form[key]"
            type="number"
            :min="min"
            :max="max"
            :step="step"
            class="h-9 w-24 rounded-lg border border-line bg-surface px-2 text-right num"
          />
        </label>
        <label class="flex items-center justify-between gap-3">
          <span class="text-sm">{{ $t('settings.stars') }}</span>
          <input
            v-model="form.stars_enabled"
            type="checkbox"
            class="size-5 accent-[var(--accent)]"
          />
        </label>
      </fieldset>
      <div class="lg:col-span-2">
        <button
          type="submit"
          class="flex h-11 items-center gap-2 rounded-lg bg-accent px-5 font-semibold text-accent-ink"
          :disabled="save.isPending.value"
        >
          <Check v-if="saved" :size="18" /> {{ saved ? $t('common.saved') : $t('common.save') }}
        </button>
        <p v-if="save.isError.value" class="mt-2 text-sm text-danger" role="alert">
          {{ save.error.value?.message }}
        </p>
      </div>
    </form>
  </main>
</template>
