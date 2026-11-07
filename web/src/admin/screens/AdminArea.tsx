/**
 * Every admin screen, in one module so the area is one chunk: no other
 * account downloads any of it, and an administrator downloads it once.
 */
export { AdminOverview } from './Overview'
export { AdminTeachers } from './Teachers'
export { AdminRequesters, AdminTickets } from './HelpDesk'
export { AdminTicketView } from './AdminTicketView'
