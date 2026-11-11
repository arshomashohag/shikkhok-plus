/**
 * Record payment keeps a typed amount through a stray tap or Escape
 * [UX-10]: an untouched sheet closes at once, a changed one asks first.
 */
import { fireEvent, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Money } from '../../../core/money'
import { renderScreen } from '../../../test/render'
import { RecordPaymentSheet } from './RecordPaymentSheet'

const fetchMock = vi.fn()
beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

function open() {
  const onClose = vi.fn()
  renderScreen(
    <RecordPaymentSheet
      enrollmentId="e1"
      name="Rafiq · Physics A"
      owed={Money.fromWire('1200.00')}
      onClose={onClose}
      onRecorded={vi.fn()}
    />,
  )
  return onClose
}

const sheet = () => screen.getByRole('dialog', { name: 'Record a payment received' })

describe('RecordPaymentSheet dismissal', () => {
  it('closes at once when nothing was changed from the pre-filled amount', async () => {
    const onClose = open()
    fireEvent.mouseDown(sheet().parentElement!)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('asks before discarding a typed amount, and keeps it on Keep editing', async () => {
    const onClose = open()
    const amount = screen.getByLabelText('Amount you received')
    await userEvent.clear(amount)
    await userEvent.type(amount, '700')
    fireEvent.mouseDown(sheet().parentElement!)
    expect(onClose).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Keep editing' }))
    expect(screen.queryByRole('dialog', { name: 'Discard what you typed?' })).toBeNull()
    expect(screen.getByLabelText('Amount you received')).toHaveValue('700')
  })

  it('discards a typed amount on Escape only once told to, sending nothing', async () => {
    const onClose = open()
    await userEvent.type(screen.getByLabelText('Amount you received'), '5')
    await userEvent.keyboard('{Escape}')
    expect(onClose).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Discard' }))
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
