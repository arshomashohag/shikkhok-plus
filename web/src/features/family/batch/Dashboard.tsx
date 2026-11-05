/**
 * A seat's dashboard for its student or guardian: the teacher's
 * `DashboardView`, fed from the family endpoints.
 */
import { request } from '../../../api/client'
import type { Schemas } from '../../../api/endpoints'
import { useT } from '../../../i18n/i18n'
import type { DashboardRange } from '../../teacher/money/api'
import { DashboardView } from '../../teacher/money/SeatProgress'
import { familyPaths, type Reader } from '../reader'
import { useSeatId, useSeatIdentity } from './seat'

const enc = encodeURIComponent

export const readFamilyDashboard = (reader: Reader, seat: string, range: DashboardRange) =>
  request<Schemas['DashboardResponse']>(
    'GET',
    reader === 'me'
      ? `/v1/me/enrollments/${enc(seat)}/dashboard`
      : `/v1/children/${enc(seat)}/dashboard`,
    { query: { range } },
  )

export function FamilyDashboard({ reader }: { reader: Reader }) {
  const seat = useSeatId()
  const { t } = useT()
  const identity = useSeatIdentity(reader, seat)
  return (
    <DashboardView
      title={
        identity?.childName
          ? t('progress_of_child', identity.childName)
          : t('screen_title_progress')
      }
      subtitle={[identity?.childName, identity?.batchName].filter(Boolean).join(' · ') || undefined}
      load={(range) => readFamilyDashboard(reader, seat, range)}
      feesLink={familyPaths.fees(reader, seat)}
      cacheKey={`${reader}:${seat}`}
    />
  )
}
