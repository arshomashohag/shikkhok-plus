package com.shikkhokplus.app.feature.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.model.SignupRole
import com.shikkhokplus.app.core.network.AlreadyAddedDto
import com.shikkhokplus.app.core.network.SignupResponseDto
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * What the signup screen needs from the network.
 *
 * Declared here rather than in `core.network` for the same reason
 * [AuthRepository] is: the feature states what it needs and the
 * network layer supplies it, so the dependency points inward.
 */
interface SignupRepository {
    /**
     * Ask whether a teacher already recorded this number.
     *
     * @param phone The number the person typed
     * @return The lookup's answer, a refusal, or a transport failure
     */
    suspend fun lookup(phone: String): AuthResult<AlreadyAddedDto>

    /**
     * Create an account for a number nobody has registered.
     *
     * @param phone The number this identity is keyed on
     * @param role The claimed role; nothing verifies it
     * @param selfName The name the person chose for themselves
     * @param address Owner-private, optional on the already-added path
     * @return The new account, a refusal, or a transport failure
     */
    suspend fun signup(
        phone: String,
        role: String,
        selfName: String,
        address: String?,
    ): AuthResult<SignupResponseDto>
}

/**
 * Holds the signup screen's state. Holds no business logic [TC-9, D-31].
 *
 * Every decision is delegated to [SignupStateMapper], which is the unit
 * the tests target. This class owns the coroutine and the state holder
 * and nothing else, matching [AuthViewModel] deliberately: two screens
 * in one flow that held state differently would be two shapes for the
 * next reader to learn.
 *
 * **V1 accepts no write without connectivity** [TC-8, D-9]. A failure
 * surfaces a state the screen renders with an explicit retry
 * affordance, and [retry] runs only when the person asks.
 */
class SignupViewModel(
    private val repository: SignupRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<SignupUiState>(SignupUiState.Empty)

    /** What the screen renders. */
    val state: StateFlow<SignupUiState> = _state.asStateFlow()

    /**
     * The number the lookup ran against.
     *
     * **Exposed because the screen's `onSubmit` does not carry it.**
     * `SignupScreen` holds the typed number in its own `remember` and
     * its submit callback passes name, address and role only — a
     * contract its Robolectric tests already pin. Reaching back for the
     * number here is cheaper than widening a tested signature, and the
     * value is the same one [lookup] was called with moments earlier.
     */
    var lastPhone: String = ""
        private set

    private var lastAction: (() -> Unit)? = null


    // The last complete number looked up, so it is asked about once.
    private var lookedUp: String? = null

    /**
     * Look up a number before showing the form.
     *
     * **The lookup runs before the form, not after submission.** A
     * person whose teacher already added them should see their own
     * name pre-filled and their role locked, rather than typing a role
     * that is then overridden — which would read as the app ignoring
     * them [AC1.12.2].
     *
     * @param phone The number the person typed
     */
    fun lookup(phone: String) {
        lastPhone = phone
        lastAction = { lookup(phone) }

        // **A number still being typed is not a wrong number.** The
        // screen now calls this only when the number field is left
        // holding a well-formed number, and judging the number is the
        // field's job, not this one's. A malformed number reaching here
        // anyway returns the form to its resting state rather than
        // raising anything. The rule is NOT weakened:
        // `submit` runs the same validation, and a genuinely malformed
        // number is refused there, where the person has said they are
        // finished.
        val invalid = SignupStateMapper.validate(phone, selfName = "placeholder")
        if (invalid != null && SignupStateMapper.PHONE_KEY in invalid.fieldKeys) {
            lookedUp = null
            if (_state.value !is SignupUiState.Empty) _state.value = SignupUiState.Empty
            return
        }
        // **Once per complete number.** Further keystrokes that leave
        // the same number valid ask nothing new.
        if (phone == lookedUp) return
        lookedUp = phone

        _state.value = SignupUiState.CheckingNumber
        viewModelScope.launch {
            _state.value =
                when (val result = repository.lookup(phone)) {
                    is AuthResult.Ok -> SignupStateMapper.afterLookup(result.value)
                    is AuthResult.Refused ->
                        SignupStateMapper.afterError(result.envelope)
                    AuthResult.TransportFailure ->
                        SignupStateMapper.afterTransportFailure()
                }
        }
    }

    /**
     * Forget what was said about the number, because it is being changed.
     *
     * **Not a check.** Nothing about the new number is judged here; that
     * waits until the person leaves the field. This only stops an answer
     * about the PREVIOUS number -- a locked role, a pre-filled name, a
     * refusal -- from standing beside a number it was never about.
     */
    fun numberEdited() {
        lookedUp = null
        when (_state.value) {
            is SignupUiState.AlreadyAdded,
            is SignupUiState.Invalid,
            is SignupUiState.Failed,
            -> _state.value = SignupUiState.Empty
            else -> Unit
        }
    }

    /**
     * Submit the completed form.
     *
     * The shape check is the mapper's and runs first, so a blank name
     * never reaches the network. Whether the number is already
     * registered is **not** checked here: that is the server's
     * decision, and a client copy of it is the validation-divergence
     * path the layer rule names.
     *
     * @param phone The number this identity is keyed on
     * @param selfName The name the person chose
     * @param address Owner-private, optional
     * @param role The claimed role
     */
    fun submit(
        phone: String,
        selfName: String,
        address: String?,
        role: SignupRole,
    ) {
        lastPhone = phone
        lastAction = { submit(phone, selfName, address, role) }

        val invalid = SignupStateMapper.validate(phone, selfName)
        if (invalid != null) {
            _state.value = invalid
            return
        }

        _state.value = SignupUiState.Submitting
        viewModelScope.launch {
            _state.value =
                when (
                    val result =
                        repository.signup(
                            phone = phone,
                            role = role.wire,
                            selfName = selfName,
                            address = address?.takeIf { it.isNotBlank() },
                        )
                ) {
                    is AuthResult.Ok -> SignupStateMapper.afterSignup(result.value)
                    is AuthResult.Refused ->
                        SignupStateMapper.afterError(result.envelope)
                    AuthResult.TransportFailure ->
                        SignupStateMapper.afterTransportFailure()
                }
        }
    }

    /**
     * Repeat the last action, when the person asks.
     *
     * Never automatic: there is no local queue in V1, so a retry the
     * person did not request would be the app deciding to write
     * without connectivity [TC-8, D-9].
     */
    fun retry() {
        lastAction?.invoke()
    }
}
