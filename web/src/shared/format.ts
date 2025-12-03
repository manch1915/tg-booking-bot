export type Locale = 'ru' | 'en'

const intlLocale = (locale: Locale) => (locale === 'ru' ? 'ru-RU' : 'en-GB')

export function money(cents: number, currency: string, locale: Locale): string {
  if (currency === 'XTR') return `${cents} ★`
  const whole = cents % 100 === 0
  return new Intl.NumberFormat(intlLocale(locale), {
    style: 'currency',
    currencyDisplay: 'narrowSymbol',
    currency,
    minimumFractionDigits: whole ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(cents / 100)
}

export function time(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', timeZone }).format(
    new Date(iso),
  )
}

export function day(isoOrDate: string, locale: Locale, timeZone: string, long = false): string {
  const date = isoOrDate.length === 10 ? new Date(`${isoOrDate}T12:00:00Z`) : new Date(isoOrDate)
  return new Intl.DateTimeFormat(intlLocale(locale), {
    weekday: long ? 'long' : 'short',
    day: 'numeric',
    month: long ? 'long' : 'short',
    timeZone: isoOrDate.length === 10 ? 'UTC' : timeZone,
  }).format(date)
}

export function dateTime(iso: string, locale: Locale, timeZone: string): string {
  return `${day(iso, locale, timeZone)}, ${time(iso, timeZone)}`
}

/** Calendar date (YYYY-MM-DD) of a moment in the shop's time zone. */
export function localDate(iso: string | Date, timeZone: string): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(typeof iso === 'string' ? new Date(iso) : iso)
  return parts
}

export function minutesLabel(minutes: number, locale: Locale): string {
  if (minutes < 60) return locale === 'ru' ? `${minutes} мин` : `${minutes} min`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  if (locale === 'ru') return m ? `${h} ч ${m} мин` : `${h} ч`
  return m ? `${h} h ${m} min` : `${h} h`
}
