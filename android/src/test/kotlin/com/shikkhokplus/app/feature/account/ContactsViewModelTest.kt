package com.shikkhokplus.app.feature.account

import com.shikkhokplus.app.core.model.IdentifierKind
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.feature.account.FakeAccountRepository.Companion.refused
import com.shikkhokplus.app.feature.auth.AuthResult
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
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The Contacts screen's cards, from the server's answer [FR8.1, W6;
 * NFR3.11]: loading, both, one, the password note, and a failed read
 * retried only when asked.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ContactsViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun loaded(me: MeDto): ContactsUiState.Loaded =
        ContactsStateMapper.afterLoad(AuthResult.Ok(me)) as ContactsUiState.Loaded

    @Test
    fun `both contacts present show both cards`() {
        val state = loaded(MeDto(phone = "+8801711111111", email = "rafi@example.com"))

        assertEquals(ContactCard(IdentifierKind.PHONE, "+8801711111111"), state.phone)
        assertEquals(ContactCard(IdentifierKind.EMAIL, "rafi@example.com"), state.email)
        assertFalse(state.passwordNote)
    }

    @Test
    fun `a phone alone leaves the email card empty`() {
        val state = loaded(MeDto(phone = "+8801711111111"))

        assertTrue(state.phone.present)
        assertFalse(state.email.present)
    }

    @Test
    fun `an email alone leaves the phone card empty`() {
        val state = loaded(MeDto(email = "rafi@example.com"))

        assertFalse(state.phone.present)
        assertTrue(state.email.present)
    }

    @Test
    fun `a single present contact is still offered for removal`() {
        // The last-one rule is the server's to refuse [NFR3.11]: the card
        // is present, so Remove is offered.
        assertTrue(loaded(MeDto(email = "rafi@example.com")).email.present)
    }

    @Test
    fun `an account with no password gets the note, the server's own flag`() {
        assertTrue(loaded(MeDto(phone = "+8801711111111", hasPassword = false)).passwordNote)
    }

    @Test
    fun `the screen loads, then shows the server's answer`() = runTest(dispatcher) {
        val repository =
            FakeAccountRepository().apply { profileAnswers += AuthResult.Ok(MeDto(phone = "+8801711111111")) }
        val model = ContactsViewModel(repository)

        model.load()
        assertEquals(ContactsUiState.Loading, model.state.value)
        advanceUntilIdle()

        assertTrue((model.state.value as ContactsUiState.Loaded).phone.present)
    }

    @Test
    fun `a failed read offers a retry that reads again`() = runTest(dispatcher) {
        val repository =
            FakeAccountRepository().apply {
                profileAnswers += AuthResult.TransportFailure
                profileAnswers += AuthResult.Ok(MeDto(email = "rafi@example.com"))
            }
        val model = ContactsViewModel(repository)
        model.load()
        advanceUntilIdle()
        assertEquals(ContactsUiState.Failed(ContactsStateMapper.OFFLINE_KEY, retryable = true), model.state.value)

        model.retry()
        advanceUntilIdle()

        assertEquals(2, repository.reads)
        assertTrue(model.state.value is ContactsUiState.Loaded)
    }

    @Test
    fun `a refused read keeps the server's retryable`() {
        assertEquals(
            ContactsUiState.Failed("error.forbidden", retryable = false),
            ContactsStateMapper.afterLoad(refused("error.forbidden")),
        )
    }

    @Test
    fun `after a removal the card says so`() = runTest(dispatcher) {
        val repository =
            FakeAccountRepository().apply { profileAnswers += AuthResult.Ok(MeDto(phone = "+8801711111111")) }
        val model = ContactsViewModel(repository)

        model.load(removedKind = IdentifierKind.EMAIL)
        advanceUntilIdle()

        assertEquals(IdentifierKind.EMAIL, (model.state.value as ContactsUiState.Loaded).removedKind)
    }

    @Test
    fun `a card never prints its contact`() {
        val card = ContactCard(IdentifierKind.EMAIL, "sentinel@example.invalid")
        val state = ContactsUiState.Loaded(card, card, passwordNote = false)

        assertFalse("sentinel@example.invalid" in card.toString())
        assertFalse("sentinel@example.invalid" in state.toString())
    }
}
