/**
 * The shared Sheet's dismissal rules [UX-10] and the shared confirmation
 * [UX-8, UX-9]: a clean sheet closes on a stray tap or Escape, a dirty one
 * asks first, and a confirmation calls nothing until it is confirmed.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../i18n/i18n'
import { ConfirmSheet, Sheet } from './components'

function Form({ onClose }: { onClose: () => void }) {
  const [typed, setTyped] = useState('')
  return (
    <Sheet title="Record" onClose={onClose} dirty={typed !== ''}>
      <label htmlFor="amount">Amount</label>
      <input id="amount" value={typed} onChange={(e) => setTyped(e.target.value)} />
      <button type="button" onClick={onClose}>
        Cancel form
      </button>
    </Sheet>
  )
}

function show(onClose = vi.fn()) {
  render(
    <I18nProvider lang="en">
      <Form onClose={onClose} />
    </I18nProvider>,
  )
  return onClose
}

const backdropOf = (name: string) => screen.getByRole('dialog', { name }).parentElement!

describe('Sheet', () => {
  it('closes at once on Escape or a backdrop tap while clean', async () => {
    const onClose = show()
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
    fireEvent.mouseDown(backdropOf('Record'))
    expect(onClose).toHaveBeenCalledTimes(2)
    expect(screen.queryByRole('dialog', { name: 'Discard what you typed?' })).toBeNull()
  })

  it('does not close on a tap inside the sheet', () => {
    const onClose = show()
    fireEvent.mouseDown(screen.getByLabelText('Amount'))
    expect(onClose).not.toHaveBeenCalled()
  })

  it('asks before discarding typed input on Escape, and keeps it when told to', async () => {
    const onClose = show()
    await userEvent.type(screen.getByLabelText('Amount'), '500')
    await userEvent.keyboard('{Escape}')
    expect(onClose).not.toHaveBeenCalled()
    const ask = screen.getByRole('dialog', { name: 'Discard what you typed?' })
    // The safe choice has focus, so a second Enter or Escape keeps the input.
    expect(screen.getByRole('button', { name: 'Keep editing' })).toHaveFocus()
    expect(ask).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: 'Discard what you typed?' })).toBeNull()
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Amount')).toHaveValue('500')
  })

  it('asks before discarding typed input on a backdrop tap, and discards when told to', async () => {
    const onClose = show()
    await userEvent.type(screen.getByLabelText('Amount'), '500')
    fireEvent.mouseDown(backdropOf('Record'))
    expect(onClose).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Discard' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('lets the sheet’s own Cancel close a dirty sheet without asking', async () => {
    const onClose = show()
    await userEvent.type(screen.getByLabelText('Amount'), '500')
    await userEvent.click(screen.getByRole('button', { name: 'Cancel form' }))
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('dialog', { name: 'Discard what you typed?' })).toBeNull()
  })

  it('becomes clean again once the input is cleared', async () => {
    const onClose = show()
    const amount = screen.getByLabelText('Amount')
    await userEvent.type(amount, '5')
    await userEvent.clear(amount)
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

describe('ConfirmSheet', () => {
  function confirmSheet() {
    const onConfirm = vi.fn()
    const onCancel = vi.fn()
    render(
      <I18nProvider lang="en">
        <ConfirmSheet
          title="Remove this place?"
          body="Rafiq will be removed."
          confirmLabel="Remove"
          onConfirm={onConfirm}
          onCancel={onCancel}
        />
      </I18nProvider>,
    )
    return { onConfirm, onCancel }
  }

  it('calls onConfirm only from its confirm button', async () => {
    const { onConfirm, onCancel } = confirmSheet()
    expect(screen.getByRole('dialog', { name: 'Remove this place?' })).toHaveTextContent(
      'Rafiq will be removed.',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(onCancel).not.toHaveBeenCalled()
  })

  it('calls only onCancel from Cancel, Escape or the backdrop', async () => {
    const { onConfirm, onCancel } = confirmSheet()
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await userEvent.keyboard('{Escape}')
    fireEvent.mouseDown(backdropOf('Remove this place?'))
    expect(onCancel).toHaveBeenCalledTimes(3)
    expect(onConfirm).not.toHaveBeenCalled()
  })
})
