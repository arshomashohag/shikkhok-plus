/** Students & notices area: Students tab, Add student (T8), Notices tab, Dues reminders. */
import type { TeacherRoute } from '../area'
import { AddStudent } from './AddStudent'
import './students.css'

export { StudentsTab } from './StudentsTab'
export { NoticesTab } from './NoticesTab'

export const studentsRoutes: TeacherRoute[] = [
  { path: '/batches/:batchId/students/new', element: <AddStudent /> },
]
