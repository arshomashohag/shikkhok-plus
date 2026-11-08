package com.shikkhokplus.app.feature.auth

import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.core.model.IdentifierKind
import com.shikkhokplus.app.core.model.PostalAddress
import com.shikkhokplus.app.core.model.SignupRole
import com.shikkhokplus.app.core.network.AlreadyAddedDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.SignupResponseDto
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * The signup ViewModel's own state machine.
 *
 * [SignupStateMapper] already covers the mapping decisions; this file
 * covers what only the ViewModel has — the in-flight states, the
 * shape check that keeps a bad form off the network, and the
 * **explicit retry** [TC-8, D-9] requires because V1 accepts no write
 * without connectivity.
 *
 * This is the half that did not exist. D1 shipped the screen, the
 * state and the mapper with tests, and no ViewModel and no repository,
 * so nothing could reach the server and the screen was unreachable.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class SignupViewModelTest {

    private companion object {
        val HOME = PostalAddress("House 12", "Road 5", "Dhaka", "1205")
    }


    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @AfterTest
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private class FakeRepository(
        var lookupResult: AuthResult<AlreadyAddedDto> =
            AuthResult.Ok(AlreadyAddedDto(alreadyAdded = false)),
        var signupResult: AuthResult<SignupResponseDto> =
            AuthResult.Ok(SignupResponseDto("acc-1", "+8801700000000")),
    ) : SignupRepository {
        var lookupCalls = 0
        var signupCalls = 0
        val sentRoles = mutableListOf<Pair<String, String?>>()

        override suspend fun lookup(phone: String): AuthResult<AlreadyAddedDto> {
            lookupCalls++
            return lookupResult
        }

        val sentIdentifiers = mutableListOf<Identifier>()

        override suspend fun signup(
            identifier: Identifier,
            role: String,
            selfName: String,
            address: PostalAddress,
            centreName: String?,
        ): AuthResult<SignupResponseDto> {
            signupCalls++
            sentIdentifiers += identifier
            sentRoles += role to centreName
            return signupResult
        }
    }

    private fun refused(
        key: String,
        retryable: Boolean,
    ) = ErrorEnvelope(ErrorBody(code = "REFUSED", messageKey = key, retryable = retryable))

    /** A complete form, by phone unless an identifier is given. */
    private fun form(
        phone: String,
        selfName: String = "Rahim",
        address: PostalAddress = HOME,
        role: SignupRole = SignupRole.STUDENT,
        centreName: String? = null,
        identifier: Identifier = Identifier.phone(phone),
        password: String = "correct horse",
        confirm: String = password,
    ) = SignupForm(identifier, selfName, address, role, password, confirm, centreName)

    @Test
    fun `editing the number drops what was said about the old one`() = runTest(dispatcher) {
        // A locked role or a refusal about the previous number must not
        // stand beside a number it was never about.
        val repo =
            FakeRepository(
                lookupResult =
                    AuthResult.Ok(AlreadyAddedDto(alreadyAdded = true, displayName = "Rahim", role = "student")),
            )
        val model = SignupViewModel(repo)
        model.lookup("+8801700000000")
        advanceUntilIdle()
        assertIs<SignupUiState.AlreadyAdded>(model.state.value)

        model.numberEdited()

        assertEquals(SignupUiState.Empty, model.state.value)
    }

    @Test
    fun `editing the number lets the same number be looked up again`() = runTest(dispatcher) {
        val repo = FakeRepository()
        val model = SignupViewModel(repo)
        model.lookup("+8801700000000")
        advanceUntilIdle()

        model.numberEdited()
        model.lookup("+8801700000000")
        advanceUntilIdle()

        assertEquals(2, repo.lookupCalls)
    }

    @Test
    fun `editing the number while it is being checked changes nothing`() = runTest(dispatcher) {
        val model = SignupViewModel(FakeRepository())
        model.lookup("+8801700000000")

        model.numberEdited()

        assertEquals(SignupUiState.CheckingNumber, model.state.value)
    }

    @Test
    fun `a refusal about the old number is dropped when it is edited`() = runTest(dispatcher) {
        val model =
            SignupViewModel(FakeRepository(lookupResult = AuthResult.Refused(refused("phone.invalid", false))))
        model.lookup("+8801700000000")
        advanceUntilIdle()
        assertIs<SignupUiState.Failed>(model.state.value)

        model.numberEdited()

        assertEquals(SignupUiState.Empty, model.state.value)
    }

    @Test
    fun `a number with no seat gives the empty form`() = runTest(dispatcher) {
        val repo = FakeRepository()
        val model = SignupViewModel(repo)

        model.lookup("+8801700000000")
        advanceUntilIdle()

        assertEquals(SignupUiState.Empty, model.state.value)
        assertEquals(1, repo.lookupCalls)
    }

    @Test
    fun `a recorded number locks the role and pre-fills the name`() =
        runTest(dispatcher) {
            // The reason the lookup runs BEFORE the form: a person
            // whose teacher already added them should not type a role
            // that is then silently overridden.
            val repo =
                FakeRepository(
                    lookupResult =
                        AuthResult.Ok(
                            AlreadyAddedDto(
                                alreadyAdded = true,
                                displayName = "Rahim",
                                role = "student",
                            ),
                        ),
                )
            val model = SignupViewModel(repo)

            model.lookup("+8801700000000")
            advanceUntilIdle()

            val state = assertIs<SignupUiState.AlreadyAdded>(model.state.value)
            assertEquals("Rahim", state.prefilledName)
            assertEquals(SignupRole.STUDENT, state.lockedRole)
        }

    @Test
    fun `an incomplete number never reaches the network`() = runTest(dispatcher) {
        // Format only, never policy: this checks the number looks like
        // a number. Whether it is already registered is the server's
        // decision and is not duplicated here.
        val repo = FakeRepository()
        val model = SignupViewModel(repo)

        model.lookup("12")
        advanceUntilIdle()

        assertEquals(0, repo.lookupCalls, "a short number must not be sent")
    }

    @Test
    fun `typing a number one character at a time raises no error`() =
        runTest(dispatcher) {
            // **The defect this exists to prevent, found on a device.**
            // The screen calls lookup on EVERY keystroke, so the first
            // character arrives long before a whole number does. An
            // earlier version reported the length rule against each
            // prefix, so typing "0" produced "that is not a number"
            // and it never cleared — every later keystroke was also
            // too short.
            //
            // The state must stay at rest until there is enough to ask
            // the server about. The rule is not weakened: submit still
            // validates, where the person has said they are finished.
            val repo = FakeRepository()
            val model = SignupViewModel(repo)

            "01711".forEachIndexed { i, _ ->
                model.lookup("01711".take(i + 1))
                advanceUntilIdle()
                assertEquals(
                    SignupUiState.Empty,
                    model.state.value,
                    "a partial number must not raise an error: ${"01711".take(i + 1)}",
                )
            }

            assertEquals(0, repo.lookupCalls, "no prefix may be sent")
        }

    @Test
    fun `a malformed number is refused on submit`() = runTest(dispatcher) {
        // The rule still bites — at the point the person says they are
        // done, rather than while they are typing.
        val repo = FakeRepository()
        val model = SignupViewModel(repo)

        model.submit(form("12"))
        advanceUntilIdle()

        assertIs<SignupUiState.Invalid>(model.state.value)
        assertEquals(0, repo.signupCalls, "a bad number must not be sent")
    }

    @Test
    fun `a blank name never reaches the network`() = runTest(dispatcher) {
        val repo = FakeRepository()
        val model = SignupViewModel(repo)

        model.submit(form("+8801700000000", selfName = "  "))
        advanceUntilIdle()

        assertIs<SignupUiState.Invalid>(model.state.value)
        assertEquals(0, repo.signupCalls, "a blank name must not be sent")
    }

    @Test
    fun `a successful signup names where the code went`() = runTest(dispatcher) {
        val repo = FakeRepository()
        val model = SignupViewModel(repo)

        model.submit(form("+8801700000000"))
        advanceUntilIdle()

        val state = assertIs<SignupUiState.CodeSent>(model.state.value)
        assertEquals("+8801700000000", state.codeSentTo)
    }

    @Test
    fun `a server refusal carries the server's own message and retryability`() =
        runTest(dispatcher) {
            // The client decides neither. A number already registered
            // arrives through here like any other refusal: the server
            // names the string and says whether retrying would help.
            val repo =
                FakeRepository(
                    signupResult =
                        AuthResult.Refused(refused("signup.already_registered", false)),
                )
            val model = SignupViewModel(repo)

            model.submit(form("+8801700000000"))
            advanceUntilIdle()

            val state = assertIs<SignupUiState.Failed>(model.state.value)
            assertEquals("signup.already_registered", state.messageKey)
            assertEquals(false, state.retryable)
        }

    @Test
    fun `a transport failure is retryable and retry repeats the last action`() =
        runTest(dispatcher) {
            // **Never automatic.** There is no local queue in V1, so a
            // retry the person did not ask for would be the app
            // deciding to write without connectivity.
            val repo = FakeRepository(signupResult = AuthResult.TransportFailure)
            val model = SignupViewModel(repo)

            model.submit(form("+8801700000000"))
            advanceUntilIdle()

            val state = assertIs<SignupUiState.Failed>(model.state.value)
            assertEquals(true, state.retryable)
            assertEquals(1, repo.signupCalls)

            model.retry()
            advanceUntilIdle()
            assertEquals(2, repo.signupCalls, "retry must repeat the submit")
        }

    @Test
    fun `the phone from the lookup is what submit sends`() = runTest(dispatcher) {
        // The screen's onSubmit carries name, address and role only,
        // so the number has to come from here. If this drifted, signup
        // would post a blank number and the server would refuse
        // something the person never typed.
        val repo = FakeRepository()
        val model = SignupViewModel(repo)

        model.lookup("+8801711111111")
        advanceUntilIdle()

        assertEquals("+8801711111111", model.lastPhone)
    }

    @Test
    fun `a complete number is looked up once, however often the field changes`() =
        runTest(dispatcher) {
            val repo = FakeRepository()
            val model = SignupViewModel(repo)

            model.lookup("+8801711111111")
            advanceUntilIdle()
            model.lookup("+8801711111111")
            advanceUntilIdle()

            assertEquals(1, repo.lookupCalls)

            model.lookup("+88017")
            advanceUntilIdle()
            model.lookup("+8801711111111")
            advanceUntilIdle()
            assertEquals(2, repo.lookupCalls, "a number edited back to complete is asked again")
        }

    @Test
    fun `a coaching sign-up sends the centre's name, trimmed`() = runTest(dispatcher) {
        val repo = FakeRepository()
        val model = SignupViewModel(repo)

        model.submit(form("+8801700000000", "Rahima", role = SignupRole.COACHING, centreName = "  Udayan Coaching "))
        advanceUntilIdle()

        assertEquals(listOf<Pair<String, String?>>("coaching" to "Udayan Coaching"), repo.sentRoles)
    }

    @Test
    fun `any other role sends no centre name`() = runTest(dispatcher) {
        val repo = FakeRepository()
        val model = SignupViewModel(repo)

        model.submit(form("+8801700000000", role = SignupRole.TEACHER, centreName = "Stale"))
        advanceUntilIdle()

        assertEquals(listOf<Pair<String, String?>>("teacher" to null), repo.sentRoles)
    }

    @Test
    fun `an email sign-up sends the email and asks nothing about a number`() = runTest(dispatcher) {
        val repo = FakeRepository(signupResult = AuthResult.Ok(SignupResponseDto("acc-1", "rafi@example.com")))
        val model = SignupViewModel(repo)

        model.kindChanged(IdentifierKind.EMAIL)
        model.submit(form("", identifier = Identifier.email("rafi@example.com")))
        advanceUntilIdle()

        assertEquals(listOf(Identifier.email("rafi@example.com")), repo.sentIdentifiers)
        assertEquals(0, repo.lookupCalls)
        assertEquals(SignupUiState.CodeSent("rafi@example.com", IdentifierKind.EMAIL), model.state.value)
    }

    @Test
    fun `a malformed email is refused on submit and never sent`() = runTest(dispatcher) {
        val repo = FakeRepository()
        val model = SignupViewModel(repo)

        model.submit(form("", identifier = Identifier.email("rafi.example.com")))
        advanceUntilIdle()

        assertEquals(SignupUiState.Invalid(listOf(SignupStateMapper.EMAIL_KEY)), model.state.value)
        assertEquals(0, repo.signupCalls)
    }

    @Test
    fun `a short or mismatched password is refused on submit and never sent`() = runTest(dispatcher) {
        val repo = FakeRepository()
        val model = SignupViewModel(repo)

        model.submit(form("+8801700000000", password = "short"))
        assertEquals(SignupUiState.Invalid(listOf(PasswordRules.TOO_SHORT_KEY)), model.state.value)

        model.submit(form("+8801700000000", password = "correct horse", confirm = "correct horsE"))
        assertEquals(SignupUiState.Invalid(listOf(PasswordRules.MISMATCH_KEY)), model.state.value)

        advanceUntilIdle()
        assertEquals(0, repo.signupCalls)
    }

    @Test
    fun `the password is handed over once, and only after the account exists`() = runTest(dispatcher) {
        val repo = FakeRepository(signupResult = AuthResult.TransportFailure)
        val model = SignupViewModel(repo)

        model.submit(form("+8801700000000"))
        advanceUntilIdle()
        assertEquals(null, model.takePassword(), "no account, so nothing to hand over")

        repo.signupResult = AuthResult.Ok(SignupResponseDto("acc-1", "+8801700000000"))
        model.retry()
        advanceUntilIdle()

        assertEquals("correct horse", model.takePassword())
        assertEquals(null, model.takePassword(), "this ViewModel keeps no copy after handing it over")
    }

    @Test
    fun `the form never prints a password`() {
        val printed = form("+8801700000000", password = "correct horse").toString()

        assertTrue("correct horse" !in printed)
    }

    @Test
    fun `a ViewModel that is cleared drops the password it held`() = runTest(dispatcher) {
        val store = androidx.lifecycle.ViewModelStore()
        val model =
            androidx.lifecycle.ViewModelProvider(
                store,
                object : androidx.lifecycle.ViewModelProvider.Factory {
                    @Suppress("UNCHECKED_CAST")
                    override fun <T : androidx.lifecycle.ViewModel> create(modelClass: Class<T>): T =
                        SignupViewModel(FakeRepository()) as T
                },
            )[SignupViewModel::class.java]
        model.submit(form("+8801700000000"))
        advanceUntilIdle()

        store.clear()

        assertEquals(null, model.takePassword())
    }
}
