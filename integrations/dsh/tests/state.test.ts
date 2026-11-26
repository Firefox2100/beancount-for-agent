import { describe, expect, it } from 'vitest'
import { fold, initialState } from '../src/state.ts'
import { stateRecord, turnEnd } from './helpers.ts'

describe('session state', () => {
  it('starts with recording on, analysis off and no ledger', () => {
    expect(initialState()).toEqual({ ledger: null, groups: { record: true, analysis: false }, turns: 0 })
  })

  it('counts ended turns', () => {
    expect(fold(fold(initialState(), turnEnd()), turnEnd()).turns).toBe(2)
  })

  it('follows ledger and group records, each change leaving the rest alone', () => {
    let state = fold(initialState(), stateRecord({ ledger: 'personal' }))
    state = fold(state, stateRecord({ groups: { analysis: true } }))
    expect(state).toEqual({ ledger: 'personal', groups: { record: true, analysis: true }, turns: 0 })
    state = fold(state, stateRecord({ groups: { record: false } }))
    expect(state.groups).toEqual({ record: false, analysis: true })
    expect(state.ledger).toBe('personal')
  })

  it('ignores records it does not understand and events that are not its own', () => {
    const state = initialState()
    expect(fold(state, stateRecord({ ledger: 12 }))).toBe(state)
    expect(fold(state, { type: 'user/message' } as never)).toBe(state)
  })

  it('is replayable: the same log gives the same state', () => {
    const log = [stateRecord({ ledger: 'a' }), turnEnd(), stateRecord({ ledger: 'b' }), turnEnd()]
    expect(log.reduce(fold, initialState())).toEqual(log.reduce(fold, initialState()))
    expect(log.reduce(fold, initialState()).ledger).toBe('b')
  })
})
