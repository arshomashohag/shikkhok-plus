package com.shikkhokplus.app.feature.auth

import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.core.model.IdentifierKind
import com.shikkhokplus.app.core.model.PostalAddress
import com.shikkhokplus.app.core.model.emailIsWellFormed
import com.shikkhokplus.app.core.model.SignupRole
import com.shikkhokplus.app.core.network.AlreadyAddedDto
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.SignupResponseDto

/**
 * Maps signup responses to a [SignupUiState].
 *
 * **This object is the unit under test**, rather than "the ViewModel".
 * It is pure: no network, no storage, no clock.
 */
object SignupStateMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The key shown when a response cannot be understood. */
    const val UNEXPECTED_KEY: String = "error.unexpected"

    /** The key shown beside a number field that is not a number. */
    const val PHONE_KEY: String = "signup.phone.invalid"

    /** The key shown beside an empty name field. */
    const val NAME_KEY: String = "signup.name.required"

    /** A part of the address missing, or a postcode that is not four digits. */
    const val ADDRESS_KEY: String = "signup.address.required"

    /** The key shown beside an email field that is not an address. Client-side only. */
    const val EMAIL_KEY: String = "signup.email.invalid"

    /**
     * Map the already-added lookup.
     *
     * **Three outcomes and no fourth.** A number with no seat gives
     * the empty form; a number with one gives a role-locked form; and a
     * response claiming a seat without a role this app knows is a
     * failure rather than a half-locked form, because locking the role
     * to a guess is worse than not locking it [BR4.5]. No name is read:
     * the lookup no longer returns one [C-06].
     *
     * @param dto The lookup's answer
     * @return The state the screen renders
     */
    fun afterLookup(dto: AlreadyAddedDto): SignupUiState {
        if (!dto.alreadyAdded) {
            return SignupUiState.Empty
        }

        val role =
            SignupRole.fromWire(dto.role)
                ?: return SignupUiState.Failed(UNEXPECTED_KEY, retryable = false)
        return SignupUiState.AlreadyAdded(lockedRole = role)
    }

    /**
     * Check the form's shape before submitting it.
     *
     * **Format only, never policy** [team: Layer boundaries]. This
     * checks that a number looks like a number and a name is not
     * blank. It does not check whether the number already has an
     * account, which is a server decision -- duplicating it here is
     * the validation-divergence erosion path, and the client's copy
     * would be the one that went stale.
     *
     * The address is required in its four parts (decided 2026-11-05);
     * only its shape is checked here -- each part filled in, the
     * postcode four digits -- and the server checks the same.
     *
     * @param phone The typed number
     * @param selfName The typed name
     * @param address The typed address
     * @return [SignupUiState.Invalid] with a key per bad field, or null
     *   when the form may be submitted
     */
    fun validate(
        phone: String,
        selfName: String,
        address: PostalAddress,
    ): SignupUiState.Invalid? {
        val problems = mutableListOf<String>()
        if (phone.length !in MIN_PHONE..MAX_PHONE || !phone.any { it.isDigit() }) {
            problems.add(PHONE_KEY)
        }
        if (selfName.isBlank()) {
            problems.add(NAME_KEY)
        }
        if (!address.isComplete) {
            problems.add(ADDRESS_KEY)
        }
        return if (problems.isEmpty()) null else SignupUiState.Invalid(problems)
    }

    /**
     * Check the whole form: the identifier of either kind, the name, the
     * address, and the password with its confirmation.
     *
     * **Format only, never policy**, as [validate] for a number: an email
     * must look like an address, a password must be 8 to 128 characters
     * and typed the same twice. Whether the password is too common, and
     * whether the phone or email already has an account, are the server's
     * to say.
     *
     * @param form What was typed
     * @return [SignupUiState.Invalid] with a key per bad field, or null
     *   when the form may be submitted
     */
    fun validate(form: SignupForm): SignupUiState.Invalid? {
        val problems = mutableListOf<String>()
        val identifier = form.identifier
        when (identifier.kind) {
            IdentifierKind.PHONE ->
                validate(identifier.value, form.selfName, form.address)?.let { problems += it.fieldKeys }
            IdentifierKind.EMAIL -> {
                if (!emailIsWellFormed(identifier.value)) problems += EMAIL_KEY
                validate(VALID_SHAPED_PHONE, form.selfName, form.address)?.let { problems += it.fieldKeys }
            }
        }
        PasswordRules.check(form.password, form.confirm)?.let { problems += it }
        return if (problems.isEmpty()) null else SignupUiState.Invalid(problems)
    }

    /**
     * Map a successful signup.
     *
     * @param dto The server's answer
     * @param kind Whether the account was keyed on a phone or an email
     * @return The code-sent state, naming the destination
     */
    fun afterSignup(
        dto: SignupResponseDto,
        kind: IdentifierKind = IdentifierKind.PHONE,
    ): SignupUiState = SignupUiState.CodeSent(dto.codeSentTo, kind)

    /**
     * Map a server error envelope.
     *
     * The number-already-registered refusal arrives through here like
     * any other: the server names the string and says whether a retry
     * would help [BR4.4, TC-9].
     *
     * @param envelope The server's error
     * @return The state the screen renders
     */
    fun afterError(envelope: ErrorEnvelope): SignupUiState =
        SignupUiState.Failed(
            messageKey = envelope.error.messageKey,
            retryable = envelope.error.retryable,
        )

    /**
     * Map a transport failure, where no envelope was received.
     *
     * @return The offline state
     */
    fun afterTransportFailure(): SignupUiState =
        SignupUiState.Failed(OFFLINE_KEY, retryable = true)

    /**
     * A number of the right shape, standing in while only the name and
     * address of an email sign-up are judged by [validate].
     */
    private const val VALID_SHAPED_PHONE = "01700000000"

    /** The shortest number the API accepts. */
    private const val MIN_PHONE = 8

    /** The longest number the API accepts. */
    private const val MAX_PHONE = 20
}

/**
 * Everything the sign-up form submits.
 *
 * Bundled because the form has grown past a readable argument list, and
 * because the password and its confirmation travel together.
 *
 * **[toString] leaves both passwords out**, so a stray log line or a
 * test failure message can never print one.
 *
 * @property identifier The phone or email this identity is keyed on
 * @property selfName The name the person chose for themselves
 * @property address Owner-private, in its four parts; required
 * @property role The claimed role
 * @property password The password chosen; sent after the code is verified
 * @property confirm The password typed a second time
 * @property centreName The coaching centre to open; with Coaching only
 */
data class SignupForm(
    val identifier: Identifier,
    val selfName: String,
    val address: PostalAddress,
    val role: SignupRole,
    val password: String,
    val confirm: String,
    val centreName: String? = null,
) {
    override fun toString(): String =
        "SignupForm(identifier=$identifier, selfName=$selfName, role=$role, centreName=$centreName, password=***)"
}
