/**
 * Students and guardians read the same screens about one seat: a student
 * reads their own (`/v1/me/...`), a guardian reads a child's
 * (`/v1/children/...`). Android calls this the reader (`FamilyReader`);
 * each family screen is written once and given one.
 *
 * The reader shapes URLs and which endpoint is called. It authorizes
 * nothing: the server checks the lens on every request [D-2].
 */
export type Reader = 'me' | 'child'

const id = (s: string) => encodeURIComponent(s)

/** The URL prefix for one seat's screens. */
export function seatBase(reader: Reader, seat: string): string {
  return reader === 'me' ? `/my/${id(seat)}` : `/child/${id(seat)}`
}

/** The router pattern matching {@link seatBase}. */
export function seatPattern(reader: Reader): string {
  return reader === 'me' ? '/my/:seat' : '/child/:seat'
}

/** Every family URL, so the areas link to each other by function. */
export const familyPaths = {
  batch: (r: Reader, seat: string) => seatBase(r, seat),
  session: (r: Reader, seat: string, sessionId: string) =>
    `${seatBase(r, seat)}/classes/${id(sessionId)}`,
  exam: (r: Reader, seat: string, examId: string) => `${seatBase(r, seat)}/exams/${id(examId)}`,
  marksheet: (r: Reader, seat: string, examId: string) =>
    `${seatBase(r, seat)}/exams/${id(examId)}/marksheet`,
  notice: (r: Reader, seat: string, noticeId: string) =>
    `${seatBase(r, seat)}/notices/${id(noticeId)}`,
  progress: (r: Reader, seat: string) => `${seatBase(r, seat)}/progress`,
  dashboard: (r: Reader, seat: string) => `${seatBase(r, seat)}/dashboard`,
  fees: (r: Reader, seat: string) => `${seatBase(r, seat)}/fees`,
  pay: (r: Reader, seat: string) => `${seatBase(r, seat)}/pay`,
  payments: (r: Reader, seat: string) => `${seatBase(r, seat)}/payments`,
} as const

/**
 * A guardian's reviews [H4]: the list, and one batch's review. By batch,
 * not by seat: two children in one batch make one review.
 */
export const reviewPaths = {
  list: () => '/reviews',
  editor: (batchId: string) => `/reviews/${id(batchId)}`,
} as const

/** Screens every signed-in person has, whatever their lens. */
export const accountPaths = {
  inbox: () => '/inbox',
  inboxItem: (notificationId: string) => `/inbox/${id(notificationId)}`,
  /** The caller's own join requests [H5]; every lens may have sent one. */
  myEnquiries: () => '/hub-enquiries',
  profileEdit: () => '/profile/edit',
  myChildren: () => '/profile/children',
  deleteAccount: () => '/profile/delete',
} as const
