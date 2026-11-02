package com.shikkhokplus.app.feature.paymentmethods

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
import kotlin.test.assertIs
import kotlin.test.assertTrue

/** P2 and P3: adding or editing one method. */
@OptIn(ExperimentalCoroutinesApi::class)
class MethodEditorViewModelTest {

    private val dispatcher = StandardTestDispatcher()
    private val repo = FakePaymentMethodsRepository()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    @Test
    fun `the dropdown offers the servers services`() {
        val model = MethodEditorViewModel(repo, services = listOf("bKash", "Nagad", "Rocket"))

        assertEquals(
            listOf("bKash", "Nagad", "Rocket").map { ProviderOption.Service(it) },
            model.providerOptions(),
        )
    }

    @Test
    fun `typed text filters services and adds a use-typed option`() {
        val model = MethodEditorViewModel(repo, services = listOf("bKash", "Nagad", "Rocket"))

        model.setProvider("Up")

        assertEquals(
            listOf(ProviderOption.UseTyped("Up")),
            model.providerOptions(),
        )
        model.setProvider("na")
        assertEquals(
            listOf(ProviderOption.Service("Nagad"), ProviderOption.UseTyped("na")),
            model.providerOptions(),
        )
    }

    @Test
    fun `typing an exact service name adds no use-typed option`() {
        val model = MethodEditorViewModel(repo, services = listOf("bKash", "Nagad", "Rocket"))

        model.setProvider("nagad")

        assertEquals(listOf(ProviderOption.Service("Nagad")), model.providerOptions())
    }

    @Test
    fun `mobile save needs a service and a number`() {
        val model = MethodEditorViewModel(repo)
        assertFalse(model.state.value.canSave)
        model.setProvider("bKash")
        assertFalse(model.state.value.canSave)
        model.setMobileNumber("01712345678")
        assertTrue(model.state.value.canSave)
    }

    @Test
    fun `bank save stays disabled until all four fields are filled`() {
        val model = MethodEditorViewModel(repo)
        model.selectKind(MethodKind.BANK)
        assertFalse(model.state.value.canSave)
        model.setAccountNumber("123")
        assertFalse(model.state.value.canSave)
        model.setAccountName("Rahima")
        assertFalse(model.state.value.canSave)
        model.setProvider("Dutch-Bangla Bank")
        assertFalse(model.state.value.canSave)
        model.setBranchName("   ")
        assertFalse(model.state.value.canSave)
        model.setBranchName("Mirpur")
        assertTrue(model.state.value.canSave)
    }

    @Test
    fun `saving a mobile method sends only the mobile fields and the optional note`() = runTest {
        val model = MethodEditorViewModel(repo)
        model.setProvider("bKash")
        model.setMobileNumber("01712345678")
        model.setNote("")

        model.save()
        advanceUntilIdle()

        assertIs<MethodEditorStatus.Saved>(model.state.value.status)
        assertEquals(
            PaymentMethodDraft(
                kind = MethodKind.MOBILE,
                provider = "bKash",
                mobileNumber = "01712345678",
                note = null,
            ),
            repo.created.single(),
        )
    }

    @Test
    fun `editing replaces the whole method`() = runTest {
        val model =
            MethodEditorViewModel(repo, existing = FakePaymentMethodsRepository.bankMethod())
        assertEquals("Rahima Akter", model.state.value.accountName)

        model.setBranchName("Uttara")
        model.save()
        advanceUntilIdle()

        val (id, draft) = repo.updated.single()
        assertEquals("b1", id)
        assertEquals(MethodKind.BANK, draft.kind)
        assertEquals("Uttara", draft.branchName)
        assertEquals("1234564521", draft.accountNumber)
        assertTrue(repo.created.isEmpty())
    }

    @Test
    fun `save_failure_keeps_the_form_and_shows_retry`() = runTest {
        repo.writeResult = AuthResult.TransportFailure
        val model = MethodEditorViewModel(repo)
        model.setProvider("bKash")
        model.setMobileNumber("01712345678")

        model.save()
        advanceUntilIdle()

        val state = model.state.value
        val failed = assertIs<MethodEditorStatus.Failed>(state.status)
        assertTrue(failed.retryable)
        assertEquals("bKash", state.provider)
        assertEquals("01712345678", state.mobileNumber)

        repo.writeResult = AuthResult.Ok(FakePaymentMethodsRepository.mobileMethod())
        model.retry()
        advanceUntilIdle()
        assertIs<MethodEditorStatus.Saved>(model.state.value.status)
        assertEquals(2, repo.created.size)
    }

    @Test
    fun `a server refusal keeps the form and carries its message key`() = runTest {
        repo.writeResult = FakePaymentMethodsRepository.refusal("fees.method.fields_incomplete")
        val model = MethodEditorViewModel(repo)
        model.setProvider("bKash")
        model.setMobileNumber("017")

        model.save()
        advanceUntilIdle()

        val failed = assertIs<MethodEditorStatus.Failed>(model.state.value.status)
        assertEquals("fees.method.fields_incomplete", failed.messageKey)
        assertFalse(failed.retryable)
        assertEquals("017", model.state.value.mobileNumber)
    }

    @Test
    fun `switching kind keeps the form editable`() {
        val model = MethodEditorViewModel(repo)
        model.selectKind(MethodKind.BANK)
        assertEquals(MethodKind.BANK, model.state.value.kind)
    }

    @Test
    fun `switching mobile to bank clears the provider and disables save until a bank name is typed`() {
        val model = MethodEditorViewModel(repo)
        model.setProvider("bKash")
        model.selectKind(MethodKind.BANK)
        model.setAccountNumber("123")
        model.setAccountName("Rahima")
        model.setBranchName("Mirpur")

        assertEquals("", model.state.value.provider)
        assertFalse(model.state.value.canSave)
        model.setProvider("Dutch-Bangla Bank")
        assertTrue(model.state.value.canSave)
    }

    @Test
    fun `the bank form offers no service suggestions`() {
        val model = MethodEditorViewModel(repo)
        model.selectKind(MethodKind.BANK)
        assertEquals(emptyList(), model.providerOptions())
        model.setProvider("b")
        assertEquals(emptyList(), model.providerOptions())
    }

    @Test
    fun `re-selecting the same kind keeps what was typed`() {
        val model = MethodEditorViewModel(repo)
        model.setProvider("bKash")
        model.selectKind(MethodKind.MOBILE)
        assertEquals("bKash", model.state.value.provider)
    }
}
