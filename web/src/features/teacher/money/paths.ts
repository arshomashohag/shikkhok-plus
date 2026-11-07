/**
 * The money area's seat links, now in the shared `teacher/paths.ts`.
 * Kept as an alias so the area's imports read as before.
 */
import { paths, readSeatNames, seatState } from '../paths'

export const moneyPaths = {
  seatFees: paths.seatFees,
  seatProgress: paths.seatProgress,
}

export { readSeatNames, seatState }
