import '@/styles/base.css'

type Lang = 'ru' | 'en'

const toggle = document.querySelector<HTMLButtonElement>('#lang')
const KEY = 'bb.landing-lang'

function read(): Lang {
  try {
    const saved = localStorage.getItem(KEY)
    if (saved === 'ru' || saved === 'en') return saved
  } catch {
    // Storage may be blocked; fall back to the browser language.
  }
  return navigator.language.startsWith('ru') ? 'ru' : 'en'
}

function apply(lang: Lang): void {
  document.documentElement.lang = lang
  for (const node of document.querySelectorAll<HTMLElement>('[data-ru]')) {
    node.textContent = node.dataset[lang] ?? node.textContent
  }
  if (toggle) toggle.textContent = lang === 'ru' ? 'EN' : 'RU'
  try {
    localStorage.setItem(KEY, lang)
  } catch {
    // Not important for a landing page.
  }
}

let current = read()
apply(current)
toggle?.addEventListener('click', () => {
  current = current === 'ru' ? 'en' : 'ru'
  apply(current)
})

// The bot username comes from the API so one build works for any bot.
fetch('/api/app/business')
  .then((r) => (r.ok ? (r.json() as Promise<{ bot_username: string }>) : null))
  .then((business) => {
    const link = document.querySelector<HTMLAnchorElement>('#bot')
    if (business && link) link.href = `https://t.me/${business.bot_username}`
  })
  .catch(() => undefined)
