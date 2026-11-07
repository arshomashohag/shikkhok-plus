/** Every help-centre URL. */
const id = encodeURIComponent

export const helpPaths = {
  list: () => '/help',
  ask: () => '/help/new',
  ticket: (ticketId: string) => `/help/${id(ticketId)}`,
} as const
