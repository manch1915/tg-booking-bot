import { describe, expect, it } from 'vitest'

import { localDate, minutesLabel, money, time } from './format'

describe('format', () => {
  it('prints whole amounts without cents', () => {
    expect(money(2800, 'USD', 'en')).toBe('$28')
    expect(money(1750, 'USD', 'en')).toBe('$17.50')
    expect(money(550, 'XTR', 'ru')).toBe('550 ★')
  })

  it('shows times in the shop time zone', () => {
    expect(time('2026-10-22T10:30:00Z', 'Asia/Yerevan')).toBe('14:30')
    expect(localDate('2026-10-22T21:30:00Z', 'Asia/Yerevan')).toBe('2026-10-23')
  })

  it('labels durations', () => {
    expect(minutesLabel(45, 'ru')).toBe('45 мин')
    expect(minutesLabel(75, 'en')).toBe('1 h 15 min')
  })
})
