package com.shikkhokplus.app.feature.hublisting

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.auth.AuthResult

/** A listing as the server answers it; tests override only what they look at. */
internal fun owner(
    status: String = "draft",
    publicName: String = "Rahima",
    slug: String? = null,
    headlineEn: String? = null,
    bioBn: String? = null,
    districtCode: String? = null,
    upazilaCode: String? = null,
    checklist: List<HubChecklistItem> = emptyList(),
    publishable: Boolean = false,
    runsClasses: Boolean = false,
    consentVersionCurrent: String = "2026-11-14",
    isCentre: Boolean = false,
) = OwnerListingResponse(
    status = status,
    slug = slug,
    publicName = publicName,
    headlineEn = headlineEn,
    bioBn = bioBn,
    districtCode = districtCode,
    upazilaCode = upazilaCode,
    checklist = checklist,
    publishable = publishable,
    runsClasses = runsClasses,
    consentVersionCurrent = consentVersionCurrent,
    isCentre = isCentre,
)

/** A batch listing as the server answers it. */
internal fun batchListing(
    id: String = "b-1",
    name: String = "Physics 9",
    status: String = "draft",
    fee: Money? = null,
    teacherNames: List<String> = emptyList(),
    checklist: List<HubChecklistItem> = emptyList(),
    publishable: Boolean = false,
    showFee: Boolean? = null,
) = BatchListingResponse(
    batchId = id,
    batchName = name,
    subjects = listOf("Physics"),
    status = status,
    showFee = showFee,
    fee = fee,
    teacherNames = teacherNames,
    checklist = checklist,
    publishable = publishable,
)

/** An in-memory [HubApi] that records what it was asked to send. */
internal class FakeHubApi : HubApi {
    var listing: AuthResult<OwnerListingResponse> = AuthResult.Ok(owner())
    var saveResult: AuthResult<OwnerListingResponse>? = null
    var publishResult: AuthResult<OwnerListingResponse>? = null
    var unpublishResult: AuthResult<OwnerListingResponse>? = null
    var slug: AuthResult<SlugAvailability>? = null
    var areasFail = false
    var batches: AuthResult<List<BatchListingResponse>> = AuthResult.Ok(emptyList())
    var batchSave: AuthResult<BatchListingResponse>? = null
    var batchPublish: AuthResult<BatchListingResponse>? = null
    var batchUnpublish: AuthResult<BatchListingResponse>? = null
    var memberships: AuthResult<List<CentreMembership>> = AuthResult.Ok(emptyList())
    var consentResult: AuthResult<Unit> = AuthResult.Ok(Unit)

    val saved = mutableListOf<OwnerListingUpdateRequest>()
    val published = mutableListOf<String>()
    var unpublished = 0
    val slugsChecked = mutableListOf<String>()
    val batchSaved = mutableListOf<Pair<String, BatchListingUpdateRequest>>()
    val batchPublished = mutableListOf<String>()
    val batchUnpublished = mutableListOf<String>()
    val consents = mutableListOf<Pair<String, Boolean>>()

    private val tree =
        mapOf(
            null to listOf("BD10" to "division", "BD20" to "division"),
            "BD20" to listOf("BD2019" to "district", "BD2020" to "district"),
            "BD10" to listOf("BD1001" to "district"),
            "BD2019" to listOf("BD201901" to "upazila"),
            "BD1001" to listOf("BD100101" to "upazila"),
        )

    override suspend fun listing(): AuthResult<OwnerListingResponse> = listing

    override suspend fun save(body: OwnerListingUpdateRequest): AuthResult<OwnerListingResponse> {
        saved += body
        return saveResult ?: AuthResult.Ok(owner())
    }

    override suspend fun publish(consentVersion: String): AuthResult<OwnerListingResponse> {
        published += consentVersion
        return publishResult ?: AuthResult.Ok(owner(status = "published", publishable = true))
    }

    override suspend fun unpublish(): AuthResult<OwnerListingResponse> {
        unpublished++
        return unpublishResult ?: AuthResult.Ok(owner(status = "hidden"))
    }

    override suspend fun slugAvailable(slug: String): AuthResult<SlugAvailability> {
        slugsChecked += slug
        return this.slug ?: AuthResult.Ok(SlugAvailability(slug, available = true))
    }

    override suspend fun areas(parent: String?): AuthResult<List<AreaOption>> =
        if (areasFail) {
            AuthResult.TransportFailure
        } else {
            val rows = tree[parent].orEmpty().map { (code, kind) -> AreaOption(code, kind, "En $code", "Bn $code") }
            AuthResult.Ok(rows)
        }

    override suspend fun batchListings(): AuthResult<List<BatchListingResponse>> = batches

    override suspend fun saveBatch(batchId: String, body: BatchListingUpdateRequest): AuthResult<BatchListingResponse> {
        batchSaved += batchId to body
        return batchSave ?: AuthResult.Ok(batchListing(id = batchId))
    }

    override suspend fun publishBatch(batchId: String): AuthResult<BatchListingResponse> {
        batchPublished += batchId
        return batchPublish ?: AuthResult.Ok(batchListing(id = batchId, status = "published"))
    }

    override suspend fun unpublishBatch(batchId: String): AuthResult<BatchListingResponse> {
        batchUnpublished += batchId
        return batchUnpublish ?: AuthResult.Ok(batchListing(id = batchId, status = "hidden"))
    }

    override suspend fun centreMemberships(): AuthResult<List<CentreMembership>> = memberships

    override suspend fun setNameConsent(centreId: String, consent: Boolean): AuthResult<Unit> {
        consents += centreId to consent
        return consentResult
    }
}
