/** Students & notices area: Students tab, Add student (T8), Notices tab, Dues reminders. */
import { NotOnWebYet } from '../../common/NotOnWebYet'
import type { BatchTabProps, TeacherRoute } from '../area'
export { StudentsTab } from './StudentsTab'

export function NoticesTab(_props: BatchTabProps) {
  return <NotOnWebYet />
}

export const studentsRoutes: TeacherRoute[] = []
