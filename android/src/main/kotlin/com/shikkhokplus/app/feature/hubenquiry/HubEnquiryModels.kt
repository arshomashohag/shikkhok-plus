package com.shikkhokplus.app.feature.hubenquiry

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.hublisting.ClassLevel
import com.shikkhokplus.app.feature.hublisting.HUB_OFFLINE_KEY
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/*
 * Join requests on the wire, and the closed tables that word them [H5].
 *
 * **Nothing here decides anything the server owns.** Who may ask is the
 * target read's answer; which answers the owner may give is
 * `outcomes_allowed`; whether the guardian's contact is shown is whether
 * the server sent one. These types carry the values and name the words.
 */

/** The longest student name the server accepts, once stripped (`EnquiryWrite`). */
const val STUDENT_NAME_MAX: Int = 80

/** The longest message the server accepts, once stripped (`EnquiryWrite`). */
const val ENQUIRY_MESSAGE_MAX: Int = 300

/** The code every switch-gated read answers with while join requests are off. */
internal const val HUB_ENQUIRIES_OFF: String = "HUB_ENQUIRIES_OFF"

/** The code a send answers when a request with this owner is already open. */
internal const val ENQUIRY_ALREADY_OPEN: String = "ENQUIRY_ALREADY_OPEN"

/** What "share" would share, as the target read names it. */
internal const val CONTACT_KIND_PHONE: String = "phone"

/** A request's status while the owner has not answered it. */
internal const val STATUS_OPEN: String = "open"

/**
 * Who a request would reach, and what "share" would share.
 *
 * @property ownerPublicName Whoever would receive the request
 * @property batchTitle The batch's public title, or null for the owner as a whole
 * @property contactKind `phone` when the account has one, else `email`
 * @property alreadyOpen The caller already has a request open with this owner
 */
@Serializable
data class EnquiryTarget(
    @SerialName("owner_public_name") val ownerPublicName: String,
    @SerialName("batch_title") val batchTitle: String? = null,
    @SerialName("contact_kind") val contactKind: String,
    @SerialName("already_open") val alreadyOpen: Boolean,
)

/**
 * A request as `POST …/enquiries` takes it. No field has a default, so the
 * consent and the declaration are always sent as chosen: the encoder omits
 * a default, and an omitted `share_contact` is a refusal, not a choice.
 *
 * @property studentName 1 to [STUDENT_NAME_MAX] characters once stripped
 * @property classLevel One of [ClassLevel]'s wire values
 * @property message The message, or null for none
 * @property batchId The batch asked about, or null for the owner
 * @property shareContact Whether the guardian chose to share their contact
 * @property declaresAdultGuardian Always true; the server refuses anything else
 */
@Serializable
data class EnquiryWrite(
    @SerialName("student_name") val studentName: String,
    @SerialName("class_level") val classLevel: String,
    @SerialName("message") val message: String?,
    @SerialName("batch_id") val batchId: String?,
    @SerialName("share_contact") val shareContact: Boolean,
    @SerialName("declares_adult_guardian") val declaresAdultGuardian: Boolean,
) {
    // A child's name and a family's words [H5: never logged].
    override fun toString(): String = "EnquiryWrite(classLevel=$classLevel, shareContact=$shareContact, text=***)"
}

/**
 * One of the caller's own requests.
 *
 * @property id The request, to withdraw it
 * @property ownerPublicName The listing's public name, or null once the listing is gone
 * @property batchTitle The batch's public title, or null
 * @property studentName As sent
 * @property classLevel One of the hub class levels
 * @property message As sent, or null
 * @property shareContact Whether the caller shared their contact
 * @property status `open` or `closed`
 * @property outcome How the owner answered, or null while open
 * @property sentOn The day it was sent, `yyyy-MM-dd`
 * @property ownerContactPhone The owner's published number, only on a `call_us` answer
 */
@Serializable
data class MyEnquiry(
    @SerialName("id") val id: String,
    @SerialName("owner_public_name") val ownerPublicName: String? = null,
    @SerialName("batch_title") val batchTitle: String? = null,
    @SerialName("student_name") val studentName: String,
    @SerialName("class_level") val classLevel: String,
    @SerialName("message") val message: String? = null,
    @SerialName("share_contact") val shareContact: Boolean,
    @SerialName("status") val status: String,
    @SerialName("outcome") val outcome: String? = null,
    @SerialName("sent_on") val sentOn: String,
    @SerialName("owner_contact_phone") val ownerContactPhone: String? = null,
) {
    // A child's name and a family's words [H5: never logged].
    override fun toString(): String = "MyEnquiry(id=$id, status=$status, outcome=$outcome)"
}

/**
 * One request, as the people who run the listing read it.
 *
 * @property id The request
 * @property batchId The batch asked about, or null for the owner as a whole
 * @property batchTitle That batch's public title, or null
 * @property studentName As the guardian typed it
 * @property classLevel One of the hub class levels
 * @property message As typed, or null
 * @property status `open` or `closed`
 * @property outcome How it was answered, or null while open
 * @property receivedAt When it was sent
 * @property guardianPhone The guardian's phone, only when they shared their contact
 * @property guardianEmail The guardian's email, only when shared and they have no phone
 * @property outcomesAllowed What a close would accept now; the screen offers exactly these
 */
@Serializable
data class OwnerEnquiry(
    @SerialName("id") val id: String,
    @SerialName("batch_id") val batchId: String? = null,
    @SerialName("batch_title") val batchTitle: String? = null,
    @SerialName("student_name") val studentName: String,
    @SerialName("class_level") val classLevel: String,
    @SerialName("message") val message: String? = null,
    @SerialName("status") val status: String,
    @SerialName("outcome") val outcome: String? = null,
    @SerialName("received_at") val receivedAt: String,
    @SerialName("guardian_phone") val guardianPhone: String? = null,
    @SerialName("guardian_email") val guardianEmail: String? = null,
    @SerialName("outcomes_allowed") val outcomesAllowed: List<String> = emptyList(),
) {
    /** The answers the server offers now, in the order the screen shows them. */
    val offered: List<EnquiryOutcome>
        get() = EnquiryOutcome.entries.filter { it.wire in outcomesAllowed }

    // A child's name, a family's words and their contact [H5: never logged].
    override fun toString(): String = "OwnerEnquiry(id=$id, status=$status, outcome=$outcome)"
}

/**
 * An answer as `POST …/close` takes it.
 *
 * @property outcome One of the request's `outcomes_allowed`
 */
@Serializable
data class EnquiryClose(
    @SerialName("outcome") val outcome: String,
)

/**
 * The owner's closed answers, in the order offered.
 *
 * @property wire The server's word
 */
enum class EnquiryOutcome(val wire: String) {
    /** The student is being added; the add-student form answers this. */
    ADDED("added"),

    /** The owner cannot take the request now. */
    NOT_NOW("not_now"),

    /** The family should call the owner's published number. */
    CALL_US("call_us"),
    ;

    companion object {
        /**
         * Name an answer.
         *
         * @param wire The server's word, if any
         * @return The answer, or null for none or one this version does not know
         */
        fun fromWire(wire: String?): EnquiryOutcome? = entries.firstOrNull { it.wire == wire }
    }
}

/**
 * A class level by its wire value.
 *
 * @param wire The server's value
 * @return The level, or null for one this version does not know
 */
fun classLevelOf(wire: String): ClassLevel? = ClassLevel.entries.firstOrNull { it.wire == wire }

/**
 * A failed call, as a screen shows it.
 *
 * @property messageKey The server's key, or the offline key
 * @property canRetry Whether repeating the call can help: the server's
 *   `retryable`, or a dropped connection
 * @property alreadyOpen Whether the refusal says a request is already open,
 *   so the screen can point to My join requests
 */
data class EnquiryFailure(
    val messageKey: String,
    val canRetry: Boolean,
    val alreadyOpen: Boolean = false,
)

/**
 * Read a failed call. Called only once the result is known not to be a
 * success: a refusal carries the server's key and `retryable`, and no
 * answer at all is the offline key, which can always be retried.
 *
 * @return The failure
 */
internal fun AuthResult<*>.enquiryFailure(): EnquiryFailure =
    (this as? AuthResult.Refused)?.envelope?.error?.let {
        EnquiryFailure(it.messageKey, it.retryable, alreadyOpen = it.code == ENQUIRY_ALREADY_OPEN)
    } ?: EnquiryFailure(HUB_OFFLINE_KEY, canRetry = true)

/** Whether a read was refused because join requests are switched off. */
internal val AuthResult<*>.isEnquiriesOff: Boolean
    get() = this is AuthResult.Refused && envelope.error.code == HUB_ENQUIRIES_OFF
