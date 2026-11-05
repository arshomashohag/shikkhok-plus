/**
 * A teacher's students, apart from any batch [0018]: the Students tab,
 * Add student with its batch multi-select, one student, and a roster's
 * "add existing students".
 */
import { lazyScreen } from '../../../core/lazy'
import type { TeacherRoute } from '../area'
import './people.css'

export const peopleRoutes: TeacherRoute[] = [
  { path: '/students', element: lazyScreen(() => import('./StudentsList'), 'StudentsList') },
  { path: '/students/new', element: lazyScreen(() => import('./NewStudent'), 'NewStudent') },
  {
    path: '/students/:studentId',
    element: lazyScreen(() => import('./StudentDetail'), 'StudentDetail'),
  },
  {
    path: '/batches/:batchId/students/pick',
    element: lazyScreen(() => import('./PickStudents'), 'PickStudents'),
  },
]
