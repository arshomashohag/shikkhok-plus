/**
 * Admin responses → what the admin screens draw. Pure, and the test
 * target.
 *
 * **The privacy boundary is the server's, and this file does not widen
 * it** [TC-14] [D-6]. A requester is named only when the server says
 * they hold a teacher or centre-member role; anyone else is a role list
 * and an opaque reference. If a name ever arrived for a student or
 * guardian alone, it is dropped here rather than shown.
 */
import type { ApiError } from '../../api/errors'
import type { Schemas } from '../../api/endpoints'
import { mapMessage, type HelpMessage, type HelpStatus } from '../help/mappers'

type T = (key: string, ...args: (string | number)[]) => string

export type Role = 'teacher' | 'centre_member' | 'student' | 'guardian'
export type Platform = 'android' | 'web'

/** A fixed order, so one person's roles always read the same way. */
const ROLE_ORDER: readonly Role[] = ['teacher', 'centre_member', 'student', 'guardian']

export const ROLE_KEY: Record<Role, string> = {
  teacher: 'web_admin_role_teacher',
  centre_member: 'web_admin_role_centre_member',
  student: 'web_admin_role_student',
  guardian: 'web_admin_role_guardian',
}

export const PLATFORM_KEY: Record<Platform, string> = {
  android: 'web_admin_platform_android',
  web: 'web_admin_platform_web',
}

/** What support sees for each status. */
export const ADMIN_STATUS_KEY: Record<HelpStatus, string> = {
  open: 'web_admin_status_open',
  answered: 'web_admin_status_answered',
  closed: 'web_admin_status_closed',
}

const STATUSES: readonly HelpStatus[] = ['open', 'answered', 'closed']

/** A `?status=` value, or null for anything else. */
export function statusParam(raw: string | null): HelpStatus | null {
  return STATUSES.includes(raw as HelpStatus) ? (raw as HelpStatus) : null
}

/** True when the server refused because this account is not an administrator. */
export function isNotAdmin(error: ApiError): boolean {
  return error.status === 403
}

// -------------------------------------------------------------- requester

export interface Requester {
  ref: string
  roles: Role[]
  /** Only for someone who holds a teacher or centre-member role. */
  name: string | null
  /** Only for a centre member. */
  centre: string | null
}

export function mapRequester(r: Schemas['AdminRequester']): Requester {
  const roles = ROLE_ORDER.filter((role) => r.roles.includes(role))
  const named = roles.includes('teacher') || roles.includes('centre_member')
  return {
    ref: r.ref,
    roles,
    name: named ? (r.name ?? null) : null,
    centre: roles.includes('centre_member') ? (r.centre ?? null) : null,
  }
}

/** `#A1B2C3D4E5`: the opaque reference as it is written on screen. */
export function displayRef(ref: string): string {
  return `#${ref.toUpperCase()}`
}

export function roleList(roles: readonly Role[], t: T): string {
  return roles.length ? roles.map((r) => t(ROLE_KEY[r])).join(', ') : t('web_admin_role_none')
}

/**
 * Who asked, in one line: a teacher's or centre member's name (with the
 * centre), otherwise "Student · #A1B2C3D4E5".
 */
export function requesterLabel(r: Requester, t: T): string {
  if (r.name) return r.centre ? `${r.name} · ${r.centre}` : r.name
  return `${roleList(r.roles, t)} · ${displayRef(r.ref)}`
}

/** The second line under a named requester: their roles and reference. */
export function requesterDetail(r: Requester, t: T): string | null {
  return r.name ? `${roleList(r.roles, t)} · ${displayRef(r.ref)}` : null
}

export interface RequesterSummary {
  requester: Requester
  tickets: number
  open: number
  lastActivity: string
}

export function mapRequesters(r: Schemas['AdminRequestersResponse']): RequesterSummary[] {
  return r.requesters.map((s) => ({
    requester: mapRequester(s.requester),
    tickets: s.tickets,
    open: s.open,
    lastActivity: s.last_activity,
  }))
}

// ---------------------------------------------------------------- tickets

export interface AdminTicket {
  id: string
  subject: string
  status: HelpStatus
  platform: Platform | null
  createdAt: string
  updatedAt: string
  messageCount: number
  preview: string
  requester: Requester
}

export interface AdminThread {
  ticket: AdminTicket
  messages: HelpMessage[]
}

export function mapAdminTicket(t: Schemas['AdminTicket']): AdminTicket {
  return {
    id: t.ticket_id,
    subject: t.subject,
    status: t.status,
    platform: t.platform ?? null,
    createdAt: t.created_at,
    updatedAt: t.updated_at,
    messageCount: t.message_count,
    preview: t.preview,
    requester: mapRequester(t.requester),
  }
}

export function mapAdminTickets(r: Schemas['AdminTicketListResponse']): AdminTicket[] {
  return r.tickets.map(mapAdminTicket)
}

export function mapAdminThread(r: Schemas['AdminTicketDetailResponse']): AdminThread {
  return { ticket: mapAdminTicket(r.ticket), messages: r.messages.map(mapMessage) }
}

// ------------------------------------------------------------- workspaces

export interface Workspace {
  id: string
  kind: 'teacher' | 'centre'
  name: string | null
  platforms: Platform[]
  joinedAt: string
  lastSeenAt: string | null
  /** A solo teacher's help-centre reference, to find their tickets. */
  ref: string | null
}

export function mapWorkspaces(r: Schemas['AdminWorkspacesResponse']): Workspace[] {
  return r.workspaces.map((w) => ({
    id: w.workspace_id,
    kind: w.kind,
    name: w.name ?? null,
    platforms: [...w.platforms],
    joinedAt: w.joined_at,
    lastSeenAt: w.last_seen_at ?? null,
    ref: w.ref ?? null,
  }))
}

export function workspaceName(w: Workspace, t: T): string {
  if (w.name) return w.name
  return t(w.kind === 'centre' ? 'web_admin_unnamed_centre' : 'web_admin_unnamed_teacher')
}

/**
 * Narrow the list by name as the administrator types. Presentational
 * only: it hides rows, it decides nothing.
 */
export function filterWorkspaces(list: readonly Workspace[], query: string): Workspace[] {
  const q = query.trim().toLocaleLowerCase()
  if (!q) return [...list]
  return list.filter((w) => w.name?.toLocaleLowerCase().includes(q))
}

// --------------------------------------------------------------- overview

export interface PlatformUsage {
  platform: Platform
  accounts: number
  active7: number
  active30: number
}

/** Android then web, with zeros for an app the server has not reported yet. */
export function platformUsage(o: Schemas['AdminOverviewResponse']): PlatformUsage[] {
  return (['android', 'web'] as const).map((platform) => {
    const p = o.platforms.find((x) => x.platform === platform)
    return {
      platform,
      accounts: p?.accounts ?? 0,
      active7: p?.active_7_days ?? 0,
      active30: p?.active_30_days ?? 0,
    }
  })
}

/** A whole percentage for a bar's width, 0 when there is no total. */
export function share(part: number, total: number): number {
  if (total <= 0 || part <= 0) return 0
  return Math.min(100, Math.round((part / total) * 100))
}

/** A count with Western digits and grouping. */
export function formatCount(n: number): string {
  return new Intl.NumberFormat('en-IN').format(n)
}
