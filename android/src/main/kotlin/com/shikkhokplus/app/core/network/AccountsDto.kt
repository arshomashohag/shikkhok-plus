package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * What the already-added lookup may say about a number.
 *
 * **Three fields, and the absences are the requirement** [BR2.3,
 * AC1.12.2]. There is no teacher name, no teacher id, no batch name and
 * no batch subject here, because with any of those the lookup becomes
 * an oracle for who teaches whom, readable by anyone who can type a
 * phone number. The DTO mirrors that bound rather than trusting the
 * server to keep it: a field declared here is a field somebody will
 * eventually ask the server to fill.
 *
 * @property alreadyAdded Whether a teacher recorded this number
 * @property displayName The teacher-typed name, to pre-fill as
 *   correctable, or null when no seat exists
 * @property role The role to lock the form to, or null
 */
@Serializable
data class AlreadyAddedDto(
    @SerialName("already_added") val alreadyAdded: Boolean,
    @SerialName("display_name") val displayName: String? = null,
    val role: String? = null,
)

/**
 * Create an account for a number nobody has registered.
 *
 * **The number is typed by the person and never read from the SIM**
 * [TC-4, D-35]. There is no device-side source for this field anywhere
 * in this app, which is enforced by the release-build DEX scan rather
 * than by this comment.
 *
 * @property phone The number this identity is keyed on
 * @property role The claimed role; nothing verifies it [BR4.2]
 * @property selfName The name the person chose for themselves
 * @property address Owner-private, and optional on the already-added
 *   path
 */
@Serializable
data class SignupRequestDto(
    val phone: String,
    val role: String,
    @SerialName("self_name") val selfName: String,
    val address: String? = null,
)

/**
 * The account exists and a code is on its way.
 *
 * **No token.** Signup does not authenticate: the person verifies
 * through the existing OTP flow, which carries the seven abuse
 * controls [BR2.2].
 *
 * @property accountId The new account
 * @property codeSentTo The number the code went to, so the screen can
 *   name its destination [AC1.11.4]
 */
@Serializable
data class SignupResponseDto(
    @SerialName("account_id") val accountId: String,
    @SerialName("code_sent_to") val codeSentTo: String,
)

/**
 * One unaccepted seat, at exactly the width the server permits.
 *
 * **Batch name, subject and fee, and nothing else about that batch**
 * [BR1.4, AC1.10.1]. No attendance, no marks, no other enrollment, and
 * no write action but accept and decline [AC1.10.2].
 *
 * `feeAmount` is a [Money], so a JSON number fails to decode loudly
 * rather than being quietly converted to a double [TC-7, D-20].
 *
 * `decision` arrives decided and is **this holder's own** — never the
 * other link's. A seat whose student and guardian are different people
 * shows each state only to its own holder [BR5.2].
 *
 * @property enrollmentId The seat, which the decision routes are keyed on
 * @property batchName The class being joined
 * @property subject The subjects taught, as the teacher named them
 * @property feeAmount This seat's fee, or null when it inherits
 * @property decision `pending` or `declined`, decided server-side
 * @property role Which link this account holds, `student` or
 *   `guardian`. **The decline confirmation differs by role** [BR5.2]:
 *   a student's decline stops their fee, a guardian's leaves the
 *   student's obligation intact. Decided server-side, never inferred
 *   from the lens hint the client supplied [TC-11, D-2]
 */
@Serializable
data class InvitationDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("batch_name") val batchName: String,
    val subject: List<String> = emptyList(),
    @SerialName("fee_amount") val feeAmount: Money? = null,
    val decision: String,
    val role: String,
)

/**
 * The seat's state after this holder decided.
 *
 * @property enrollmentId The seat decided on
 * @property decision `accepted` or `declined`
 */
@Serializable
data class DecisionDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    val decision: String,
)
