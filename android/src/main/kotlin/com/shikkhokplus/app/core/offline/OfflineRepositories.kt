package com.shikkhokplus.app.core.offline

import androidx.compose.runtime.staticCompositionLocalOf
import com.shikkhokplus.app.core.network.DuesResponseDto
import com.shikkhokplus.app.core.network.FamilyBatchViewDto
import com.shikkhokplus.app.core.network.GuardianHomeDto
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.core.network.ProgressEntryDto
import com.shikkhokplus.app.core.network.StudentBatchDto
import com.shikkhokplus.app.core.network.TodayDto
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.dues.DuesRepository
import com.shikkhokplus.app.feature.guardian.GuardianRepository
import com.shikkhokplus.app.feature.profile.ProfileRepository
import com.shikkhokplus.app.feature.student.StudentRepository
import com.shikkhokplus.app.feature.today.TodayRepository
import kotlinx.serialization.builtins.ListSerializer

/**
 * The session's offline copies, or null where none are kept (a test,
 * or a screen rendered on its own).
 */
val LocalOfflineCopies = staticCompositionLocalOf<OfflineCopies?> { null }

/**
 * Today (T1), with its last read kept for offline.
 *
 * @param inner The network repository
 * @param copies Where the copy is kept
 */
class OfflineTodayRepository(
    private val inner: TodayRepository,
    private val copies: OfflineCopies,
) : TodayRepository {
    override suspend fun today(): AuthResult<TodayDto> =
        copies.through("today", TodayDto.serializer()) { inner.today() }
}

/**
 * Dues (T5), with its last read kept for offline. Reminding is never
 * answered from a copy.
 *
 * @param inner The network repository
 * @param copies Where the copy is kept
 */
class OfflineDuesRepository(
    private val inner: DuesRepository,
    private val copies: OfflineCopies,
) : DuesRepository by inner {
    override suspend fun dues(): AuthResult<DuesResponseDto> =
        copies.through("dues", DuesResponseDto.serializer()) { inner.dues() }
}

/**
 * A student's or a guardian's batches and batch pages (S1, S2), with
 * their last reads kept for offline.
 *
 * @param inner The network repository
 * @param copies Where the copies are kept
 * @param reader Whose reads these are, so a student's and a guardian's
 *   copies of one seat are never confused
 */
class OfflineStudentRepository(
    private val inner: StudentRepository,
    private val copies: OfflineCopies,
    private val reader: String,
) : StudentRepository by inner {
    override suspend fun batches(): AuthResult<List<StudentBatchDto>> =
        copies.through("$reader/batches", ListSerializer(StudentBatchDto.serializer())) { inner.batches() }

    override suspend fun phone(): AuthResult<MeDto> =
        copies.through("$reader/me", MeDto.serializer()) { inner.phone() }

    override suspend fun batchView(enrollmentId: String): AuthResult<FamilyBatchViewDto> =
        copies.through("$reader/view/$enrollmentId", FamilyBatchViewDto.serializer()) { inner.batchView(enrollmentId) }

    override suspend fun progress(enrollmentId: String): AuthResult<List<ProgressEntryDto>> =
        copies.through("$reader/progress/$enrollmentId", ListSerializer(ProgressEntryDto.serializer())) {
            inner.progress(enrollmentId)
        }
}

/**
 * The guardian's home (G1), with its last read kept for offline.
 *
 * @param inner The network repository
 * @param copies Where the copies are kept
 */
class OfflineGuardianRepository(
    private val inner: GuardianRepository,
    private val copies: OfflineCopies,
) : GuardianRepository by inner {
    override suspend fun home(): AuthResult<GuardianHomeDto> =
        copies.through("guardian/home", GuardianHomeDto.serializer()) { inner.home() }

    override suspend fun me(): AuthResult<MeDto> = copies.through("guardian/me", MeDto.serializer()) { inner.me() }
}

/**
 * More's profile card (T9, S4, G4), with its last read kept for
 * offline. Saving and deletion always go to the server.
 *
 * @param inner The network repository
 * @param copies Where the copy is kept
 */
class OfflineProfileRepository(
    private val inner: ProfileRepository,
    private val copies: OfflineCopies,
) : ProfileRepository by inner {
    override suspend fun profile(): AuthResult<MeDto> =
        copies.through("profile", MeDto.serializer()) { inner.profile() }
}

/**
 * This repository, kept offline by [copies] when the session has them.
 *
 * @param copies The session's copies, or null to keep nothing
 * @param wrap The offline repository for this kind
 * @return The wrapped repository, or this one unchanged
 */
fun <R> R.keptBy(copies: OfflineCopies?, wrap: (R, OfflineCopies) -> R): R =
    if (copies == null) this else wrap(this, copies)
