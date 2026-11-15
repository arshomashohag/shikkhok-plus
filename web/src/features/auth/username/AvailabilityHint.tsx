/**
 * The availability hint under a username field: text, never colour
 * alone, in a `role="status"` region present from Idle, so the region
 * exists before its text changes [functional-spec § 7]. Whether a real
 * screen reader announces the change is not verified, and not claimed.
 */
import { useT } from '../../../i18n/i18n'
import { availabilityText, type Availability } from './availability'

export function AvailabilityHint({
  id,
  state,
  help,
}: {
  /** Becomes the element's id, for the input's `aria-describedby`. */
  id: string
  state: Availability
  /** Shown while there is nothing to say yet. */
  help?: string
}) {
  const { t, message } = useT()
  const text = availabilityText(state, t, message)
  const answered = state.kind === 'answered' ? state.status : state.kind
  return (
    <span id={id} className="help" role="status" data-availability={answered}>
      {text ?? help ?? ''}
    </span>
  )
}
