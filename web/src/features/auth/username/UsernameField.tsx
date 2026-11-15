/**
 * A username input with its availability hint and its error slot, for
 * sign-up, the Replace step, the gate and rename.
 *
 * The client holds no username rule [FR11.3]. It only caps the input so
 * the **trimmed** value is at most 64 code points — the schema's
 * `maxLength` on every request carrying a username — in the change
 * handler, not with HTML `maxlength` (which counts UTF-16 units of the
 * untrimmed text), and not while an IME composition is in progress, so a
 * composing keyboard is never cut mid-word [NFR3.11].
 */
import type { ChangeEvent, CompositionEvent, Ref } from 'react'
import { describedBy } from '../parts'
import { AvailabilityHint } from './AvailabilityHint'
import type { Availability } from './availability'

/** The schema's `maxLength` for a username, in code points. */
export const USERNAME_MAX = 64

/**
 * `raw` with its trimmed part cut to {@link USERNAME_MAX} code points;
 * unchanged when it already fits. Leading space is kept, as typed.
 */
export function capUsername(raw: string): string {
  const trimmed = [...raw.trim()]
  if (trimmed.length <= USERNAME_MAX) return raw
  const lead = /^\s*/.exec(raw)?.[0] ?? ''
  return lead + trimmed.slice(0, USERNAME_MAX).join('')
}

interface Props {
  id: string
  label: string
  value: string
  /** Every accepted edit; the caller feeds the checker from it. */
  onChange: (value: string) => void
  availability: Availability
  /** Shown under the field while the hint has nothing to say. */
  help?: string
  error?: string | null
  disabled?: boolean
  inputRef?: Ref<HTMLInputElement>
}

export function UsernameField({
  id,
  label,
  value,
  onChange,
  availability,
  help,
  error,
  disabled,
  inputRef,
}: Props) {
  function onInput(e: ChangeEvent<HTMLInputElement>) {
    const composing = (e.nativeEvent as InputEvent).isComposing === true
    onChange(composing ? e.target.value : capUsername(e.target.value))
  }

  // The last composition step arrives as an input event still marked
  // composing, so the cap is applied when the composition ends.
  function onCompositionEnd(e: CompositionEvent<HTMLInputElement>) {
    const capped = capUsername(e.currentTarget.value)
    if (capped !== e.currentTarget.value) onChange(capped)
  }

  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        ref={inputRef}
        id={id}
        name="username"
        type="text"
        autoComplete="username"
        autoCapitalize="none"
        spellCheck={false}
        value={value}
        disabled={disabled}
        onChange={onInput}
        onCompositionEnd={onCompositionEnd}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, true, Boolean(error))}
      />
      <AvailabilityHint id={`${id}-help`} state={availability} help={help} />
      {error ? (
        <span id={`${id}-error`} className="field-error" role="alert">
          {error}
        </span>
      ) : null}
    </div>
  )
}
