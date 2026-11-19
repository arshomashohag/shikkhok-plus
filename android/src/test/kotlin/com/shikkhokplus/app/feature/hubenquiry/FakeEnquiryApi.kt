package com.shikkhokplus.app.feature.hubenquiry

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.CompletableDeferred

/**
 * The join-request routes in memory: each call is recorded, and answered
 * with the next queued result for its route, the last one repeating.
 */
internal class FakeEnquiryApi :
    EnquirerApi,
    OwnerEnquiriesApi {

    /** Every call, as `METHOD what`. */
    val calls = mutableListOf<String>()

    /** Every request body sent. */
    val sent = mutableListOf<EnquiryWrite>()

    var targets: List<AuthResult<EnquiryTarget>> = listOf(AuthResult.Ok(target()))
    var sends: List<AuthResult<MyEnquiry>> = listOf(AuthResult.Ok(myEnquiry()))
    var mine: List<AuthResult<List<MyEnquiry>>> = listOf(AuthResult.Ok(emptyList()))
    var withdrawals: List<AuthResult<Unit>> = listOf(AuthResult.Ok(Unit))
    var inbox: List<AuthResult<List<OwnerEnquiry>>> = listOf(AuthResult.Ok(emptyList()))
    var reads: List<AuthResult<OwnerEnquiry>> = listOf(AuthResult.Ok(ownerEnquiry()))
    var closes: List<AuthResult<OwnerEnquiry>> = listOf(AuthResult.Ok(ownerEnquiry(status = "closed")))

    /** When set, a close waits for it before answering, so a test can act mid-flight. */
    var closeGate: CompletableDeferred<Unit>? = null

    private val counts = mutableMapOf<String, Int>()

    private fun <T> next(route: String, queue: List<AuthResult<T>>): AuthResult<T> {
        val n = counts.getOrDefault(route, 0)
        counts[route] = n + 1
        return queue[minOf(n, queue.size - 1)]
    }

    override suspend fun target(ownerSlug: String, batchId: String?): AuthResult<EnquiryTarget> {
        calls += "GET target $ownerSlug $batchId"
        return next("target", targets)
    }

    override suspend fun send(ownerSlug: String, body: EnquiryWrite): AuthResult<MyEnquiry> {
        calls += "POST $ownerSlug"
        sent += body
        return next("send", sends)
    }

    override suspend fun mine(): AuthResult<List<MyEnquiry>> {
        calls += "GET mine"
        return next("mine", mine)
    }

    override suspend fun withdraw(enquiryId: String): AuthResult<Unit> {
        calls += "DELETE $enquiryId"
        return next("withdraw", withdrawals)
    }

    override suspend fun inbox(): AuthResult<List<OwnerEnquiry>> {
        calls += "GET inbox"
        return next("inbox", inbox)
    }

    override suspend fun read(enquiryId: String): AuthResult<OwnerEnquiry> {
        calls += "GET $enquiryId"
        return next("read", reads)
    }

    override suspend fun close(enquiryId: String, outcome: EnquiryOutcome): AuthResult<OwnerEnquiry> {
        calls += "CLOSE $enquiryId ${outcome.wire}"
        closeGate?.await()
        return next("close", closes)
    }
}

/** A refusal as the server sends it. */
internal fun refused(code: String, key: String, retryable: Boolean = false): AuthResult<Nothing> =
    AuthResult.Refused(ErrorEnvelope(ErrorBody(code, retryable, key)))

/** Join requests are switched off. */
internal val enquiriesOff: AuthResult<Nothing> = refused("HUB_ENQUIRIES_OFF", "hub.enquiry.off")

/** What the form reads before the guardian sends. */
internal fun target(
    owner: String = "Rahima",
    batch: String? = "Physics 9",
    contactKind: String = "phone",
    alreadyOpen: Boolean = false,
) = EnquiryTarget(ownerPublicName = owner, batchTitle = batch, contactKind = contactKind, alreadyOpen = alreadyOpen)

/** One of the guardian's own requests. */
internal fun myEnquiry(
    id: String = "e-1",
    owner: String? = "Rahima",
    status: String = "open",
    outcome: String? = null,
    phone: String? = null,
) = MyEnquiry(
    id = id,
    ownerPublicName = owner,
    batchTitle = "Physics 9",
    studentName = "Nadia",
    classLevel = "class_8",
    shareContact = true,
    status = status,
    outcome = outcome,
    sentOn = "2026-11-19",
    ownerContactPhone = phone,
)

/** One request as its owner reads it. */
internal fun ownerEnquiry(
    id: String = "e-1",
    status: String = "open",
    outcome: String? = null,
    phone: String? = null,
    email: String? = null,
    allowed: List<String> = if (status == "open") listOf("added", "not_now", "call_us") else emptyList(),
) = OwnerEnquiry(
    id = id,
    batchId = "b-1",
    batchTitle = "Physics 9",
    studentName = "Nadia",
    classLevel = "class_8",
    message = "Wants Physics",
    status = status,
    outcome = outcome,
    receivedAt = "2026-11-19T06:00:00Z",
    guardianPhone = phone,
    guardianEmail = email,
    outcomesAllowed = allowed,
)
