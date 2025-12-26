<script setup lang="ts">
import { Check, Clock, Star, Users } from 'lucide-vue-next'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { minutesLabel, money } from '@/shared/format'
import { photo } from '@/shared/photo'

import Avatar from '../components/Avatar.vue'
import LoadState from '../components/LoadState.vue'
import PageHeader from '../components/PageHeader.vue'
import { useMainAction } from '../composables/mainAction'
import { draft } from '../draft'
import { useCatalog, useOffers } from '../queries'
import { locale, session } from '../session'
import { haptic } from '../telegram'

const props = defineProps<{ id: number }>()
const router = useRouter()
const { t } = useI18n()
const catalog = useCatalog()
const offers = useOffers(() => props.id)
const lang = computed(() => locale())

const service = computed(() =>
  catalog.data.value?.categories.flatMap((c) => c.services).find((s) => s.id === props.id),
)
const cheapest = computed(() => Math.min(...(offers.data.value ?? []).map((o) => o.price)))

if (draft.serviceId !== props.id) {
  draft.serviceId = props.id
  draft.masterId = null
}

function price(cents: number): string {
  return money(cents, session.business!.currency, lang.value)
}

function choose(masterId: number | null): void {
  haptic()
  draft.masterId = masterId
}

useMainAction(
  () => ({ text: t('service.pick'), visible: !!service.value }),
  () => {
    haptic('light')
    draft.startsAt = null
    void router.push({ name: 'time' })
  },
)
</script>

<template>
  <main>
    <PageHeader back="/" />
    <LoadState
      :loading="catalog.isPending.value"
      :error="catalog.isError.value"
      @retry="catalog.refetch()"
    />
    <template v-if="service">
      <div class="mx-4 overflow-hidden rounded-[22px] bg-surface-2">
        <img
          :src="photo(service.photo_url, 400, 275)"
          :alt="service.name[lang]"
          class="aspect-[16/11] w-full object-cover"
        />
      </div>
      <section class="px-4 pt-4">
        <h1 class="font-sign text-[34px] leading-[1] font-bold">{{ service.name[lang] }}</h1>
        <p class="mt-2 flex items-center gap-1.5 text-sm text-muted">
          <Clock :size="16" :stroke-width="1.75" />
          {{ minutesLabel(service.duration_minutes, lang) }}
        </p>
        <p class="mt-3 text-[15px] leading-relaxed text-ink/85">{{ service.description[lang] }}</p>
      </section>

      <section class="px-4 pt-6" aria-labelledby="who">
        <h2 id="who" class="pb-2 font-sign text-xl font-semibold">{{ $t('service.who') }}</h2>
        <div class="overflow-hidden rounded-[18px] bg-surface" role="radiogroup">
          <button
            type="button"
            role="radio"
            :aria-checked="draft.masterId === null"
            class="flex w-full items-center gap-3 border-b border-line p-3 text-left"
            @click="choose(null)"
          >
            <span class="grid size-12 place-items-center rounded-full bg-accent-soft text-accent">
              <Users :size="22" :stroke-width="1.75" />
            </span>
            <span class="flex-1">
              <span class="block font-semibold">{{ $t('common.anyMaster') }}</span>
              <span class="text-sm text-muted">
                {{ $t('common.anyMasterHint') }}
              </span>
            </span>
            <span v-if="offers.data.value" class="font-sign text-lg font-semibold num">
              {{ $t('common.from', { price: price(cheapest) }) }}
            </span>
            <Check v-if="draft.masterId === null" :size="20" class="text-accent" />
          </button>
          <button
            v-for="offer in offers.data.value ?? []"
            :key="offer.master.id"
            type="button"
            role="radio"
            :aria-checked="draft.masterId === offer.master.id"
            class="flex w-full items-center gap-3 border-b border-line p-3 text-left last:border-b-0"
            @click="choose(offer.master.id)"
          >
            <Avatar
              :src="offer.master.photo_url"
              :name="offer.master.name[lang]"
              :color="offer.master.color"
            />
            <span class="min-w-0 flex-1">
              <span class="block font-semibold">{{ offer.master.name[lang] }}</span>
              <span class="flex items-center gap-1 text-sm text-muted">
                {{ offer.master.title[lang] }}
                <template v-if="offer.master.rating">
                  <Star :size="12" class="ml-1 fill-brass text-brass" />
                  <span class="num">{{ offer.master.rating.toFixed(1) }}</span>
                </template>
              </span>
            </span>
            <span class="font-sign text-lg font-semibold num">{{ price(offer.price) }}</span>
            <Check v-if="draft.masterId === offer.master.id" :size="20" class="text-accent" />
          </button>
        </div>
      </section>
    </template>
  </main>
</template>
