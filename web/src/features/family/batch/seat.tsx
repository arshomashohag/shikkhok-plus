/**
 * What every family seat screen shares: the seat id from the URL, who the
 * seat is (batch, teacher, and the child's name for a guardian), and the
 * words that keep a guardian's screens attributed to one child.
 *
 * None of the read endpoints for one seat returns the batch or child name,
 * so they come from the reader's own seat list — the same rows S1 and G1
 * show, read again rather than handed through the URL, so a pasted link
 * still titles itself correctly.
 */
import { useParams } from 'react-router'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import type { Reader } from '../reader'
import { listChildSeats, listMySeats } from './api'
import { identityFromChildren, identityFromMine, type SeatIdentity } from './mappers'

export function useSeatId(): string {
  return useParams().seat ?? ''
}

/** Null while loading or when the seat is not the reader's. */
export function useSeatIdentity(reader: Reader, seat: string): SeatIdentity | null {
  const { resource } = useResource(
    (signal) =>
      reader === 'me'
        ? listMySeats(signal).then((rows) => identityFromMine(rows, seat))
        : listChildSeats(signal).then((rows) => identityFromChildren(rows, seat)),
    [reader, seat],
  )
  return resource.state === 'loaded' ? resource.data : null
}

/**
 * A section heading, attributed to the child when a guardian reads it —
 * the design's rule that one child's marks never sit under a bare title.
 *
 * @param plain The student's own heading key
 * @param childKey The `{1}`-taking guardian heading key
 */
export function useHeading() {
  const { t } = useT()
  return (identity: SeatIdentity | null, plain: string, childKey: string) =>
    identity?.childName ? t(childKey, identity.childName) : t(plain)
}

/** Title and subtitle for a seat screen's top bar, as Android's scaffold. */
export function seatTitles(identity: SeatIdentity | null): {
  batch: string | undefined
  who: string | undefined
} {
  return {
    batch: identity?.batchName,
    who: identity?.childName ?? identity?.teacherName ?? undefined,
  }
}
