import { describe, expect, it } from 'vitest'
import { applyChange, defaultLedgerState, fold, initialState, isGroup } from '../src/state.ts'
import { stateSchema } from '../src/store.ts'
import { turnEnd } from './helpers.ts'

describe('session state', () => {
  it('starts with recording on, analysis off and no ledger', () => {
    expect(defaultLedgerState()).toEqual({ ledger: null, groups: { record: true, analysis: false } })
  })

  it('projects only what the session log can tell: ended turns', () => {
    expect(initialState()).toEqual({ turns: 0 })
    expect(fold(fold(initialState(), turnEnd()), turnEnd())).toEqual({ turns: 2 })
  })

  it('leaves the projection alone for anything that is not an ended turn', () => {
    const state = initialState()
    expect(fold(state, { type: 'user/message' } as never)).toBe(state)
    expect(fold(state, { type: 'turn/start' } as never)).toBe(state)
  })

  it('applies one change at a time, leaving the rest alone', () => {
    let state = applyChange(defaultLedgerState(), { ledger: 'personal' })
    state = applyChange(state, { groups: { analysis: true } })
    expect(state).toEqual({ ledger: 'personal', groups: { record: true, analysis: true } })
    state = applyChange(state, { groups: { record: false } })
    expect(state).toEqual({ ledger: 'personal', groups: { record: false, analysis: true } })
    expect(applyChange(state, {}).ledger).toBe('personal')
  })

  it('knows the groups it offers', () => {
    expect(isGroup('record')).toBe(true)
    expect(isGroup('analysis')).toBe(true)
    expect(isGroup('everything')).toBe(false)
  })
})

describe('the stored record', () => {
  it('round-trips a session state', () => {
    const state = applyChange(defaultLedgerState(), { ledger: 'personal', groups: { record: false } })
    expect(stateSchema.parse(JSON.parse(JSON.stringify(state)))).toEqual(state)
  })

  it('rejects anything it could not read back', () => {
    expect(stateSchema.safeParse({ ledger: 12, groups: { record: true, analysis: false } }).success).toBe(false)
    expect(stateSchema.safeParse({ ledger: null, groups: { record: 'yes' } }).success).toBe(false)
  })
})
