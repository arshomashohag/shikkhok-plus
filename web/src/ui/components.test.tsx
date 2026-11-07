/** The shared Sheet: focus that stays where the person is typing. */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../i18n/i18n'
import { Sheet } from './components'

/** A caller as the screens write one: an inline onClose, a field in parent state. */
function MoveClass({ onClose }: { onClose: () => void }) {
  const [date, setDate] = useState('')
  const [time, setTime] = useState('')
  return (
    <>
      <button type="button">behind</button>
      <Sheet title="Move class" onClose={() => onClose()}>
        <label htmlFor="d">Date</label>
        <input id="d" value={date} onChange={(e) => setDate(e.target.value)} />
        <label htmlFor="t">Time</label>
        <input id="t" value={time} onChange={(e) => setTime(e.target.value)} />
        <button type="button">Save</button>
      </Sheet>
    </>
  )
}

function mount(onClose = vi.fn()) {
  render(
    <I18nProvider lang="en">
      <MoveClass onClose={onClose} />
    </I18nProvider>,
  )
  return onClose
}

describe('Sheet', () => {
  it('focuses the first field once, then leaves the cursor where the person types', async () => {
    mount()
    expect(screen.getByLabelText('Date')).toHaveFocus()
    await userEvent.click(screen.getByLabelText('Time'))
    // Every keystroke re-renders the parent with a new onClose.
    await userEvent.keyboard('1730')
    expect(screen.getByLabelText('Time')).toHaveValue('1730')
    expect(screen.getByLabelText('Date')).toHaveValue('')
    expect(screen.getByLabelText('Time')).toHaveFocus()
  })

  it('makes the page behind it inert while open, and keeps Tab inside', async () => {
    mount()
    const behind = screen.getByRole('button', { name: 'behind', hidden: true })
    expect(behind).toHaveAttribute('inert')
    screen.getByRole('button', { name: 'Save' }).focus()
    await userEvent.tab()
    expect(screen.getByLabelText('Date')).toHaveFocus()
    await userEvent.tab({ shift: true })
    expect(screen.getByRole('button', { name: 'Save' })).toHaveFocus()
  })

  it('closes on Escape, restores the background and returns focus on unmount', async () => {
    function Host() {
      const [open, setOpen] = useState(false)
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            open
          </button>
          {open ? (
            <Sheet title="Sheet" onClose={() => setOpen(false)}>
              <input aria-label="field" />
            </Sheet>
          ) : null}
        </>
      )
    }
    render(
      <I18nProvider lang="en">
        <Host />
      </I18nProvider>,
    )
    const opener = screen.getByRole('button', { name: 'open' })
    await userEvent.click(opener)
    expect(screen.getByLabelText('field')).toHaveFocus()
    expect(opener).toHaveAttribute('inert')
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByLabelText('field')).toBeNull()
    expect(opener).not.toHaveAttribute('inert')
    expect(opener).toHaveFocus()
  })
})
