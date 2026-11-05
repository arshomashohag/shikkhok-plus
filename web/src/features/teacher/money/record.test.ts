import { describe, expect, it } from 'vitest'
import { Money } from '../../../core/money'
import {
  CASH,
  RECORD_CHANNELS,
  openRecord,
  recordBody,
  recordState,
  typeRecordAmount,
} from './record'

const owed = Money.fromWire('1500.00')
const KEY = '00000000-0000-4000-8000-000000000001'

describe('the record sheet — RecordPaymentSheet in FeesViewModel.kt', () => {
  it('starts at what the server says is owed, in cash, with no choice made', () => {
    const input = openRecord(owed, KEY)
    expect(input).toMatchObject({ typed: '1500', channel: CASH, disposition: null })
    expect(RECORD_CHANNELS[0]).toBe(CASH)
    expect(recordState(owed, input)).toMatchObject({ side: 'exact', canConfirm: true })
  })

  it('starts blank when nothing is owed, rather than at a zero the server refuses', () => {
    expect(openRecord(Money.fromWire('0.00'), KEY).typed).toBe('')
  })

  it('the full amount sends no disposition and keeps the retry key', () => {
    expect(recordBody(owed, { ...openRecord(owed, KEY), note: '  Paid at the door ' })).toEqual({
      amount: '1500.00',
      channel: 'cash',
      reference: null,
      note: 'Paid at the door',
      shortfall_disposition: null,
      client_mutation_id: KEY,
    })
  })

  it('a short amount asks carry or waive and sends nothing until one is chosen', () => {
    const short = typeRecordAmount(owed, openRecord(owed, KEY), '1000')
    expect(recordState(owed, short)).toMatchObject({ side: 'short', needsDisposition: true })
    expect(recordBody(owed, short)).toBeNull()

    const carried = recordBody(owed, { ...short, disposition: 'carried' })
    expect(carried).toMatchObject({ amount: '1000.00', shortfall_disposition: 'carried' })
    const waived = recordBody(owed, { ...short, disposition: 'waived' })
    expect(waived).toMatchObject({ shortfall_disposition: 'waived' })
  })

  it('more than is owed asks nothing: the server holds the rest as credit', () => {
    const over = typeRecordAmount(owed, openRecord(owed, KEY), '2,000')
    expect(recordState(owed, over)).toMatchObject({ side: 'over', needsDisposition: false })
    expect(recordBody(owed, over)).toMatchObject({
      amount: '2000.00',
      shortfall_disposition: null,
    })
  })

  it('drops a carry-or-waive that no longer applies when the amount changes side', () => {
    const short = {
      ...typeRecordAmount(owed, openRecord(owed, KEY), '900'),
      disposition: 'waived' as const,
    }
    expect(typeRecordAmount(owed, short, '800').disposition).toBe('waived')
    expect(typeRecordAmount(owed, short, '1500').disposition).toBeNull()
  })

  it.each(['0', '0.00', '', 'abc', '-5', '1.234'])('refuses %j as an amount', (typed) => {
    const input = typeRecordAmount(owed, openRecord(owed, KEY), typed)
    expect(recordState(owed, input).side).toBe('invalid')
    expect(recordBody(owed, input)).toBeNull()
  })

  it('sends a mobile service by name with its reference, Bangla digits read', () => {
    const input = {
      ...typeRecordAmount(owed, openRecord(owed, KEY), '১৫০০'),
      channel: 'bKash',
      reference: ' 9KD7Q2XL1M ',
    }
    expect(recordBody(owed, input)).toMatchObject({
      amount: '1500.00',
      channel: 'bKash',
      reference: '9KD7Q2XL1M',
    })
  })
})
