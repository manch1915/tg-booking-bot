/** Wall-clock helpers for the shop's time zone, independent of the viewer's own zone. */

interface Parts {
  year: number
  month: number
  day: number
  hour: number
  minute: number
}

const formatters = new Map<string, Intl.DateTimeFormat>()

function formatter(timeZone: string): Intl.DateTimeFormat {
  let f = formatters.get(timeZone)
  if (!f) {
    f = new Intl.DateTimeFormat('en-US', {
      timeZone,
      hourCycle: 'h23',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
    formatters.set(timeZone, f)
  }
  return f
}

export function zonedParts(moment: Date | string, timeZone: string): Parts {
  const parts = formatter(timeZone).formatToParts(new Date(moment))
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? 0)
  return {
    year: get('year'),
    month: get('month'),
    day: get('day'),
    hour: get('hour'),
    minute: get('minute'),
  }
}

/** Minutes since local midnight in the shop. */
export function minutesOfDay(moment: Date | string, timeZone: string): number {
  const p = zonedParts(moment, timeZone)
  return p.hour * 60 + p.minute
}

/** ISO instant for a wall-clock date and time in the shop, e.g. ("2026-10-22", "14:30"). */
export function zonedToIso(date: string, time: string, timeZone: string): string {
  const [y, m, d] = date.split('-').map(Number) as [number, number, number]
  const [hh, mm] = time.split(':').map(Number) as [number, number]
  const guess = Date.UTC(y, m - 1, d, hh, mm)
  const p = zonedParts(new Date(guess), timeZone)
  const seen = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute)
  return new Date(guess - (seen - guess)).toISOString()
}

export function hhmm(minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

export function parseHhmm(value: string): number {
  const [h, m] = value.split(':').map(Number) as [number, number]
  return h * 60 + m
}

export function addDays(date: string, days: number): string {
  const d = new Date(`${date}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

export function todayIn(timeZone: string): string {
  const p = zonedParts(new Date(), timeZone)
  return `${p.year}-${String(p.month).padStart(2, '0')}-${String(p.day).padStart(2, '0')}`
}

export function mondayOf(date: string): string {
  const weekday = (new Date(`${date}T12:00:00Z`).getUTCDay() + 6) % 7
  return addDays(date, -weekday)
}
