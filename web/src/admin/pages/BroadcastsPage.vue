<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { Send } from 'lucide-vue-next'
import { computed, ref } from 'vue'

import type { Schemas } from '@/shared/api/client'
import { dateTime } from '@/shared/format'

import { api, auth } from '../api'
import { useMasters, useShop } from '../context'

const SEGMENTS = ['all', 'inactive_30', 'new_clients', 'with_bonuses', 'master_regulars'] as const

const queryClient = useQueryClient()
const { lang, tz } = useShop()
const masters = useMasters()
const segment = ref<(typeof SEGMENTS)[number]>('inactive_30')
const masterId = ref<number | null>(null)
const textRu = ref('')
const textEn = ref('')
const done = ref(false)

const audience = computed(() => ({
  segment: segment.value,
  master_id:
    segment.value === 'master_regulars'
      ? (masterId.value ?? masters.data.value?.[0]?.master.id ?? null)
      : null,
}))

const preview = useQuery({
  queryKey: ['admin', 'audience', audience],
  queryFn: () => api.post<Schemas['AudienceOut']>('/api/admin/broadcasts/preview', audience.value),
})

const history = useQuery({
  queryKey: ['admin', 'broadcasts'],
  queryFn: () => api.get<Schemas['BroadcastOut'][]>('/api/admin/broadcasts'),
})

const send = useMutation({
  mutationFn: () =>
    api.post<Schemas['BroadcastOut']>('/api/admin/broadcasts', {
      ...audience.value,
      text_ru: textRu.value,
      text_en: textEn.value,
    }),
  onSuccess: async () => {
    textRu.value = ''
    textEn.value = ''
    done.value = true
    setTimeout(() => (done.value = false), 2500)
    await queryClient.invalidateQueries({ queryKey: ['admin', 'broadcasts'] })
  },
})
</script>

<template>
  <main class="grid gap-5 p-4 lg:grid-cols-[1fr_1fr] lg:p-6">
    <section class="space-y-4">
      <h1 class="font-sign text-3xl font-semibold">{{ $t('broadcasts.compose') }}</h1>
      <form
        class="space-y-4 rounded-2xl border border-line bg-surface p-4"
        @submit.prevent="send.mutate()"
      >
        <fieldset>
          <legend class="text-sm font-semibold">{{ $t('broadcasts.audience') }}</legend>
          <div class="mt-2 flex flex-wrap gap-2">
            <label
              v-for="key in SEGMENTS"
              :key="key"
              class="cursor-pointer rounded-full px-3 py-1.5 text-sm font-semibold has-[:checked]:bg-ink has-[:checked]:text-bg"
              :class="segment === key ? '' : 'bg-surface-2 text-muted'"
            >
              <input v-model="segment" type="radio" :value="key" class="sr-only" />
              {{ $t(`clients.segment.${key}`) }}
            </label>
          </div>
          <select
            v-if="segment === 'master_regulars'"
            v-model="masterId"
            class="mt-3 h-10 w-full rounded-lg border border-line bg-surface px-2"
            :aria-label="$t('broadcasts.master')"
          >
            <option v-for="m in masters.data.value ?? []" :key="m.master.id" :value="m.master.id">
              {{ m.master.name[lang] }}
            </option>
          </select>
          <p v-if="preview.data.value" class="mt-3 text-sm text-muted">
            {{ $t('broadcasts.reach', preview.data.value) }}
          </p>
        </fieldset>
        <label class="block">
          <span class="text-sm font-semibold">{{ $t('broadcasts.textRu') }}</span>
          <textarea
            v-model="textRu"
            rows="4"
            maxlength="3500"
            class="mt-1 w-full resize-y rounded-lg border border-line bg-surface p-3"
          />
        </label>
        <label class="block">
          <span class="text-sm font-semibold">{{ $t('broadcasts.textEn') }}</span>
          <textarea
            v-model="textEn"
            rows="4"
            maxlength="3500"
            class="mt-1 w-full resize-y rounded-lg border border-line bg-surface p-3"
          />
        </label>
        <p v-if="auth.admin?.demo" class="rounded-lg bg-brass-soft p-3 text-sm text-brass">
          {{ $t('broadcasts.demoNote') }}
        </p>
        <p v-if="done" class="text-sm font-semibold text-accent" role="status">
          {{ $t('broadcasts.sent') }}
        </p>
        <button
          type="submit"
          class="flex h-11 items-center gap-2 rounded-lg bg-accent px-4 font-semibold text-accent-ink disabled:opacity-50"
          :disabled="send.isPending.value || (!textRu.trim() && !textEn.trim())"
        >
          <Send :size="16" /> {{ $t('broadcasts.send') }}
        </button>
      </form>
    </section>

    <section class="space-y-3">
      <h2 class="font-sign text-3xl font-semibold">{{ $t('broadcasts.history') }}</h2>
      <article
        v-for="b in history.data.value ?? []"
        :key="b.id"
        class="rounded-2xl border border-line bg-surface p-4"
      >
        <p class="flex flex-wrap justify-between gap-2 text-xs text-muted">
          <span
            >{{ $t(`clients.segment.${b.segment}`) }} ·
            {{ $t('broadcasts.recipients', { n: b.recipients }) }}</span
          >
          <span>{{ dateTime(b.created_at, lang, tz) }} · {{ b.created_by }}</span>
        </p>
        <p class="mt-2 text-sm whitespace-pre-line">{{ lang === 'ru' ? b.text_ru : b.text_en }}</p>
      </article>
    </section>
  </main>
</template>
