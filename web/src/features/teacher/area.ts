/**
 * The contract between the batch screen / router and each teacher area.
 */
import type { ReactElement } from 'react'
import type { BatchSummary } from './mappers'

/** A route an area owns; the router mounts it under the teacher lens. */
export interface TeacherRoute {
  /** Router path pattern, e.g. `/batches/:batchId/exams/new`. Must match `paths`. */
  path: string
  element: ReactElement
}

/** What every batch-screen tab receives. */
export interface BatchTabProps {
  batchId: string
  /** Null while the batch list could not be read; the tab still works by id. */
  batch: BatchSummary | null
  /** Re-read the batch header (name, schedule, fee) after an edit. */
  reloadBatch: () => void
}
