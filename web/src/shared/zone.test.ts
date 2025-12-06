import { describe, expect, it } from 'vitest'

import { addDays, hhmm, minutesOfDay, mondayOf, zonedToIso } from './zone'

describe('zone helpers', () => {
  it('reads wall-clock minutes in the shop zone', () => {
    expect(minutesOfDay('2026-10-22T10:30:00Z', 'Asia/Yerevan')).toBe(14 * 60 + 30)
  })

  it('turns shop wall-clock time into an instant', () => {
    expect(zonedToIso('2026-10-22', '14:30', 'Asia/Yerevan')).toBe('2026-10-22T10:30:00.000Z')
    // Across a DST change in another zone.
    expect(zonedToIso('2026-03-29', '12:00', 'Europe/Berlin')).toBe('2026-03-29T10:00:00.000Z')
  })

  it('does calendar math on plain dates', () => {
    expect(addDays('2026-10-31', 1)).toBe('2026-11-01')
    expect(mondayOf('2026-10-22')).toBe('2026-10-19')
    expect(hhmm(605)).toBe('10:05')
  })
})
