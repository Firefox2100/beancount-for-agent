import { describe, expect, it } from 'vitest'
import { fixed, grouped, heldLine } from '../src/client/money.ts'

describe('money', () => {
  it('groups thousands in the text and leaves decimals alone', () => {
    expect(grouped('123456.78')).toBe('123,456.78')
    expect(grouped('-1234567.8')).toBe('-1,234,567.8')
    expect(grouped('999')).toBe('999')
    expect(grouped('1234567890123456.789')).toBe('1,234,567,890,123,456.789')
    expect(grouped('—')).toBe('—')
  })
  it('writes held amounts and float sums the same way', () => {
    expect(heldLine({ GBP: '48469.17', USD: '30' })).toBe('48,469.17 GBP · 30 USD')
    expect(heldLine({ GBP: '1000' }, '\n')).toBe('1,000 GBP')
    expect(fixed(1234.5)).toBe('1,234.50')
  })
})
