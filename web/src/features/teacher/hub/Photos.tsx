/**
 * The Photos section of a public listing: the owner's own gallery, or one
 * batch's [H3].
 *
 * **The upload goes to the bucket, not through the API.** The server hands
 * back a presigned POST; the file is sent to it with a plain `fetch`, the
 * ticket's fields first and the file last, with no header and no
 * credential. That keeps it a CORS *simple* request: the app's own client
 * would add an `Authorization` header and force a preflight the bucket
 * need not answer, and the bucket must never be sent the session token.
 *
 * After the upload, `complete` is polled every two seconds for up to a
 * minute while the server answers `MEDIA_NOT_UPLOADED` (the file is still
 * being read). Past the minute the screen offers "Check again", which polls
 * again and does **not** upload a second time. Any other answer ends the
 * poll: a refusal is shown in the server's words.
 *
 * Every rule is the server's: type and size are only pre-checked for a
 * kinder message, the quota counts the listed photos the server counts --
 * every status but `rejected` and `withdrawn` (the server already leaves
 * out an upload abandoned past its window) -- and a photo's `thumb_url` is
 * absolute and used as it arrives. A reorder names only those counted
 * photos; the server keeps the rest after them.
 *
 * `readOnly` (a suspended listing) hides adding and reordering but keeps
 * delete: the server does not refuse a delete for a suspension (only the
 * daily edit allowance can), and a suspended listing's approved photo keeps
 * its public link until its owner removes it.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  completeHubPhoto,
  deleteHubPhoto,
  listHubPhotos,
  putHubPhotoOrder,
  startHubPhotoUpload,
  type Schemas,
} from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { useT } from '../../../i18n/i18n'
import { ConfirmSheet, Section } from '../../../ui/components'
import { failureText, FailureBanner } from './hubUi'

type Photo = Schemas['MediaResponse']
type Status = Photo['status']

/** The gallery limits, as the server states them: an owner's page, a batch's. */
export const OWNER_PHOTO_LIMIT = 12
export const BATCH_PHOTO_LIMIT = 8

const ACCEPT = 'image/jpeg,image/png,image/webp'
const TYPES: readonly string[] = ACCEPT.split(',')
/** The server's ceiling; checked here only to answer before a pointless upload. */
const MAX_BYTES = 8 * 1024 * 1024

export const POLL_INTERVAL_MS = 2000
export const POLL_LIMIT_MS = 60_000

const NOT_UPLOADED = 'MEDIA_NOT_UPLOADED'

/** The statuses that free a slot, as the server's quota reads them. */
const UNCOUNTED: readonly Status[] = ['rejected', 'withdrawn']
const counts = (p: Photo) => !UNCOUNTED.includes(p.status)

const STATUS_CHIP: Record<Status, string> = {
  awaiting_upload: 'chip',
  processing: 'chip',
  pending_review: 'chip',
  approved: 'chip chip-paid',
  rejected: 'chip chip-overdue',
  held: 'chip chip-overdue',
  withdrawn: 'chip',
}

interface Job {
  mediaId: string
  altEn: string
  altBn: string
  /** `uploading` and `checking` are in flight; `slow` and `retry` offer Check again. */
  phase: 'uploading' | 'checking' | 'slow' | 'retry'
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

const isNotUploaded = (e: unknown) =>
  e instanceof ApiError && (e.code === NOT_UPLOADED || e.messageKey === 'hub.media.not_uploaded')

/** Post the file to the bucket as a CORS simple request: fields first, `file` last, nothing else. */
async function postToBucket(ticket: Schemas['MediaUploadTicket'], file: File): Promise<void> {
  const form = new FormData()
  for (const [name, value] of Object.entries(ticket.fields)) form.append(name, value)
  form.append('file', file)
  let response: Response
  try {
    response = await fetch(ticket.url, { method: 'POST', body: form })
  } catch {
    throw new Error('upload')
  }
  if (!response.ok) throw new Error('upload')
}

export function Photos({
  batchId,
  readOnly = false,
}: {
  /** The batch whose gallery this is; null for the owner's own page. */
  batchId: string | null
  readOnly?: boolean
}) {
  const { t, message, lang } = useT()
  const [photos, setPhotos] = useState<Photo[] | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [altEn, setAltEn] = useState('')
  const [altBn, setAltBn] = useState('')
  const [job, setJob] = useState<Job | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [deleting, setDeleting] = useState<Photo | null>(null)
  const alive = useRef(true)
  const limit = batchId === null ? OWNER_PHOTO_LIMIT : BATCH_PHOTO_LIMIT

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  useEffect(() => {
    const ctl = new AbortController()
    setLoadFailed(false)
    listHubPhotos(batchId, ctl.signal).then(
      (list) => setPhotos(list),
      (e: unknown) => {
        if (!(e instanceof DOMException && e.name === 'AbortError')) setLoadFailed(true)
      },
    )
    return () => ctl.abort()
  }, [batchId, attempt])

  const upsert = useCallback((photo: Photo) => {
    setPhotos((list) => {
      const rest = (list ?? []).filter((p) => p.id !== photo.id)
      return [...rest, photo].sort((a, b) => a.position - b.position)
    })
  }, [])

  /** Poll `complete` until the file has been processed, a minute passes, or it is refused. */
  const poll = useCallback(
    async (next: Job) => {
      setJob({ ...next, phase: 'checking' })
      for (let waited = 0; ; waited += POLL_INTERVAL_MS) {
        try {
          const photo = await completeHubPhoto(next.mediaId, {
            alt_en: next.altEn,
            alt_bn: next.altBn,
          })
          if (!alive.current) return
          upsert(photo)
          setJob(null)
          setAltEn('')
          setAltBn('')
          return
        } catch (e) {
          if (!alive.current) return
          if (!isNotUploaded(e)) {
            setFailure(failureText(e, t, message))
            // A dropped connection can be asked again; a refusal ends this photo.
            if (e instanceof ApiError && (e.offline || e.retryable)) {
              setJob({ ...next, phase: 'retry' })
            } else {
              setJob(null)
              setAttempt((n) => n + 1)
            }
            return
          }
          if (waited >= POLL_LIMIT_MS) {
            setFailure(`${t('web_hub_photo_slow')} ${message('hub.media.not_uploaded')}`)
            setJob({ ...next, phase: 'slow' })
            return
          }
        }
        await sleep(POLL_INTERVAL_MS)
        if (!alive.current) return
      }
    },
    [message, t, upsert],
  )

  async function choose(file: File) {
    setFailure(null)
    if (altEn.trim() === '' || altBn.trim() === '') {
      setFailure(t('web_hub_photo_alt_required'))
      return
    }
    if (!TYPES.includes(file.type)) {
      setFailure(message('hub.media.type_not_allowed'))
      return
    }
    if (file.size > MAX_BYTES) {
      setFailure(message('hub.media.too_large'))
      return
    }
    const alts = { altEn: altEn.trim(), altBn: altBn.trim() }
    setJob({ mediaId: '', ...alts, phase: 'uploading' })
    let mediaId: string
    try {
      const ticket = await startHubPhotoUpload({
        batch_id: batchId,
        content_type: file.type as Schemas['MediaUploadInit']['content_type'],
        byte_size: file.size,
      })
      mediaId = ticket.media_id
      await postToBucket(ticket, file)
    } catch (e) {
      if (!alive.current) return
      setJob(null)
      setFailure(
        e instanceof ApiError ? failureText(e, t, message) : t('web_hub_photo_upload_failed'),
      )
      return
    }
    if (alive.current) await poll({ mediaId, ...alts, phase: 'uploading' })
  }

  async function run(call: () => Promise<void>) {
    setBusy(true)
    setFailure(null)
    try {
      await call()
    } catch (e) {
      setFailure(failureText(e, t, message))
    } finally {
      setBusy(false)
    }
  }

  const move = (index: number, by: -1 | 1) =>
    run(async () => {
      if (!photos) return
      const ids = photos.map((p) => p.id)
      const a = ids[index]
      const b = ids[index + by]
      if (a === undefined || b === undefined) return
      ids[index] = b
      ids[index + by] = a
      const counted = new Set(photos.filter(counts).map((p) => p.id))
      setPhotos(
        await putHubPhotoOrder(
          batchId,
          ids.filter((id) => counted.has(id)),
        ),
      )
    })

  const remove = (photo: Photo) =>
    run(async () => {
      try {
        await deleteHubPhoto(photo.id)
      } finally {
        // Closed either way: an open sheet would hide the failure banner.
        setDeleting(null)
      }
      setPhotos((list) => (list ?? []).filter((p) => p.id !== photo.id))
    })

  const inFlight = job?.phase === 'uploading' || job?.phase === 'checking'
  const list = photos ?? []

  return (
    <Section
      title={t('web_hub_photos_title')}
      aside={
        photos ? (
          <span className="meta">
            {t('web_hub_photos_count', list.filter(counts).length, limit)}
          </span>
        ) : null
      }
    >
      <p className="meta">{t('web_hub_photos_help')}</p>
      {loadFailed ? (
        <FailureBanner
          text={t('web_hub_photos_load_failed')}
          onRetry={() => setAttempt((n) => n + 1)}
        />
      ) : null}
      {photos && list.length === 0 ? <p className="meta">{t('web_hub_photos_empty')}</p> : null}
      <ul className="card flush list">
        {list.map((p, i) => {
          const alt = lang === 'bn' ? p.alt_bn || p.alt_en : p.alt_en || p.alt_bn
          return (
            <li key={p.id}>
              <div className="row">
                {p.thumb_url ? (
                  // Absolute already: the public site, or a short-lived bucket link.
                  <img
                    src={p.thumb_url}
                    alt={alt ?? ''}
                    width={64}
                    height={64}
                    style={{ objectFit: 'cover', borderRadius: 8 }}
                  />
                ) : (
                  <span
                    className="meta"
                    style={{ width: 64, height: 64, display: 'grid', placeItems: 'center' }}
                  >
                    {t('web_hub_photo_no_preview')}
                  </span>
                )}
                <span className="grow" style={{ overflowWrap: 'anywhere' }}>
                  {alt}
                  <br />
                  <span className={STATUS_CHIP[p.status]}>
                    {t(`web_hub_photo_status_${p.status}`)}
                  </span>
                </span>
                {readOnly ? null : (
                  <>
                    <button
                      type="button"
                      className="btn btn-text btn-small"
                      aria-label={t('web_hub_photo_move_up', i + 1)}
                      disabled={busy || i === 0}
                      onClick={() => void move(i, -1)}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      className="btn btn-text btn-small"
                      aria-label={t('web_hub_photo_move_down', i + 1)}
                      disabled={busy || i === list.length - 1}
                      onClick={() => void move(i, 1)}
                    >
                      ↓
                    </button>
                  </>
                )}
                {/* Even read-only: a suspended listing's photo keeps its public link until removed. */}
                <button
                  type="button"
                  className="btn btn-text btn-small"
                  aria-label={t('web_hub_photo_delete', i + 1)}
                  disabled={busy}
                  onClick={() => setDeleting(p)}
                >
                  ×
                </button>
              </div>
            </li>
          )
        })}
      </ul>

      {readOnly ? null : (
        <div className="card form-page">
          <div className="field">
            <label htmlFor={`photo-alt-en-${batchId ?? 'owner'}`}>
              {t('web_hub_photo_alt_en')}
            </label>
            <input
              id={`photo-alt-en-${batchId ?? 'owner'}`}
              value={altEn}
              maxLength={200}
              disabled={inFlight}
              onChange={(e) => setAltEn(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor={`photo-alt-bn-${batchId ?? 'owner'}`}>
              {t('web_hub_photo_alt_bn')}
            </label>
            <input
              id={`photo-alt-bn-${batchId ?? 'owner'}`}
              value={altBn}
              maxLength={200}
              disabled={inFlight}
              onChange={(e) => setAltBn(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor={`photo-file-${batchId ?? 'owner'}`}>{t('web_hub_photo_choose')}</label>
            <input
              id={`photo-file-${batchId ?? 'owner'}`}
              type="file"
              accept={ACCEPT}
              disabled={inFlight || job !== null}
              onChange={(e) => {
                const file = e.target.files?.[0]
                e.target.value = ''
                if (file) void choose(file)
              }}
            />
          </div>
          {job?.phase === 'uploading' ? (
            <p className="meta" role="status">
              {t('web_hub_photo_uploading')}
            </p>
          ) : null}
          {job?.phase === 'checking' ? (
            <p className="meta" role="status">
              {t('web_hub_photo_checking')}
            </p>
          ) : null}
        </div>
      )}

      {failure ? (
        <div className="banner error" role="alert">
          <span className="grow">{failure}</span>
          {job && (job.phase === 'slow' || job.phase === 'retry') ? (
            <button
              type="button"
              className="btn btn-text btn-small"
              onClick={() => {
                setFailure(null)
                void poll(job)
              }}
            >
              {t('web_hub_photo_check_again')}
            </button>
          ) : null}
        </div>
      ) : null}

      {deleting ? (
        <ConfirmSheet
          title={t('web_hub_photo_delete_title')}
          body={t('web_hub_photo_delete_body')}
          confirmLabel={t('web_hub_photo_delete_confirm')}
          busy={busy}
          onConfirm={() => void remove(deleting)}
          onCancel={() => setDeleting(null)}
        />
      ) : null}
    </Section>
  )
}
