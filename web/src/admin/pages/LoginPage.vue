<script setup lang="ts">
import { LoaderCircle } from 'lucide-vue-next'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { demoLogin, passwordLogin } from '../api'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const email = ref('')
const password = ref('')
const busy = ref<'demo' | 'password' | null>(null)
const error = ref('')

async function go(kind: 'demo' | 'password'): Promise<void> {
  busy.value = kind
  error.value = ''
  try {
    if (kind === 'demo') await demoLogin()
    else await passwordLogin(email.value, password.value)
    const next = typeof route.query.next === 'string' ? route.query.next : '/journal'
    await router.replace(next)
  } catch {
    error.value = t('login.wrong')
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <main class="grid min-h-dvh lg:grid-cols-[1.1fr_1fr]">
    <section class="relative hidden overflow-hidden bg-leather text-leather-ink lg:block">
      <img
        src="https://images.unsplash.com/photo-1759134198561-e2041049419c?auto=format&fit=crop&w=1400&h=1600&q=70"
        alt=""
        class="absolute inset-0 size-full object-cover opacity-35 mix-blend-luminosity"
      />
      <div class="relative flex h-full flex-col justify-between p-12">
        <span class="pole block h-3 w-28 rounded-full" aria-hidden="true" />
        <div>
          <p class="font-sign text-[88px] leading-[0.85] font-bold">Brass<br />&amp; Blade</p>
          <p class="mt-6 max-w-sm text-lg opacity-85">Tumanyan St 21, Yerevan</p>
        </div>
      </div>
    </section>

    <section class="flex items-center justify-center bg-bg px-6 py-12">
      <div class="w-full max-w-sm">
        <h1 class="font-sign text-4xl font-semibold">{{ $t('login.title') }}</h1>
        <p class="mt-2 text-muted">{{ $t('login.subtitle') }}</p>

        <button
          type="button"
          class="mt-8 flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-accent font-semibold text-accent-ink transition-transform active:scale-[0.99]"
          :disabled="busy !== null"
          @click="go('demo')"
        >
          <LoaderCircle v-if="busy === 'demo'" :size="18" class="animate-spin" />
          {{ $t('login.demo') }}
        </button>
        <p class="mt-2 text-sm text-muted">{{ $t('login.demoHint') }}</p>

        <div class="my-8 flex items-center gap-3 text-sm text-faint">
          <span class="h-px flex-1 bg-line" />{{ $t('login.or')
          }}<span class="h-px flex-1 bg-line" />
        </div>

        <form class="space-y-3" @submit.prevent="go('password')">
          <label class="block">
            <span class="text-sm font-semibold">{{ $t('login.email') }}</span>
            <input
              v-model="email"
              type="email"
              autocomplete="username"
              required
              class="mt-1 h-11 w-full rounded-xl border border-line bg-surface px-3 focus:border-accent focus:outline-none"
            />
          </label>
          <label class="block">
            <span class="text-sm font-semibold">{{ $t('login.password') }}</span>
            <input
              v-model="password"
              type="password"
              autocomplete="current-password"
              required
              class="mt-1 h-11 w-full rounded-xl border border-line bg-surface px-3 focus:border-accent focus:outline-none"
            />
          </label>
          <p v-if="error" class="text-sm text-danger" role="alert">{{ error }}</p>
          <button
            type="submit"
            class="flex h-11 w-full items-center justify-center gap-2 rounded-xl border border-line bg-surface font-semibold"
            :disabled="busy !== null"
          >
            <LoaderCircle v-if="busy === 'password'" :size="18" class="animate-spin" />
            {{ $t('login.submit') }}
          </button>
        </form>
      </div>
    </section>
  </main>
</template>
