/** Students & notices area: Students tab, Add student (T8), Notices tab, Dues reminders. */
import { lazyComponent, lazyScreen } from '../../../core/lazy'
import type { BatchTabProps, TeacherRoute } from '../area'
import './students.css'

export const StudentsTab = lazyComponent<BatchTabProps, typeof import('./StudentsTab')>(
  () => import('./StudentsTab'),
  'StudentsTab',
)
export const NoticesTab = lazyComponent<BatchTabProps, typeof import('./NoticesTab')>(
  () => import('./NoticesTab'),
  'NoticesTab',
)

export const studentsRoutes: TeacherRoute[] = [
  {
    path: '/batches/:batchId/students/new',
    element: lazyScreen(() => import('./AddStudent'), 'AddStudent'),
  },
]
