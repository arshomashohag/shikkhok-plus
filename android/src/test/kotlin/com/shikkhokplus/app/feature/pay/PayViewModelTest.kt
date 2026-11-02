package com.shikkhokplus.app.feature.pay

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.FamilyPaymentMethodsDto
import com.shikkhokplus.app.core.network.OwedChildDto
import com.shikkhokplus.app.core.network.OwedTogetherDto
import com.shikkhokplus.app.core.network.PaymentMethodDto
import com.shikkhokplus.app.core.network.PaymentSubmitDto
import com.shikkhokplus.app.core.network.PaymentSubmittedDto
import com.shikkhokplus.app.core.network.StudentBatchDto
import com.shikkhokplus.app.core.network.SubmittedClaimDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull

/**
 * The "Send money" flow: choose how, fill in, send, sent -- and that a
 * failed send keeps what was typed rather than queueing it.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class PayViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private val bkash = PaymentMethodDto("m-1", "mobile", "bKash", mobileNumber = "01712345678")
    private val bank = PaymentMethodDto("m-2", "bank", "Dutch-Bangla", accountNumber = "1051", branchName = "Mirpur")

    private fun seat(id: String, batch: String, child: String? = null, teacher: String = "Najma") =
        StudentBatchDto(id, batch, teacher, childName = child)

    private fun owed(total: String, vararg children: Pair<String, String>) =
        OwedTogetherDto(
            Money.of(total),
            children.map { (id, name) -> OwedChildDto(id, name, Money.of("0.00")) },
        )

    private fun submitted(total: String = "1000.00") =
        PaymentSubmittedDto(
            "s-1",
            "pending",
            Money.of(total),
            "2026-11-02",
            listOf(SubmittedClaimDto("c-1", Money.of(total), "Tanvir", "e-1", "2026-11")),
        )

    private class Fake(
        var seats: AuthResult<List<StudentBatchDto>>,
        var methods: AuthResult<FamilyPaymentMethodsDto>,
        var owed: AuthResult<OwedTogetherDto>,
        var submit: AuthResult<PaymentSubmittedDto>,
    ) : PayRepository {
        val sent = mutableListOf<PaymentSubmitDto>()
        val methodReads = mutableListOf<String>()
        val owedReads = mutableListOf<List<String>>()
        var gate: CompletableDeferred<Unit>? = null

        override suspend fun seats() = seats

        override suspend fun methods(enrollmentId: String): AuthResult<FamilyPaymentMethodsDto> {
            methodReads += enrollmentId
            return methods
        }

        override suspend fun owed(enrollmentIds: List<String>): AuthResult<OwedTogetherDto> {
            owedReads += enrollmentIds
            return owed
        }

        override suspend fun submit(payment: PaymentSubmitDto): AuthResult<PaymentSubmittedDto> {
            sent += payment
            gate?.await()
            return submit
        }
    }

    private fun fake(
        seats: List<StudentBatchDto> = listOf(seat("e-1", "Physics")),
        owed: AuthResult<OwedTogetherDto> = AuthResult.Ok(owed("1000.00", "e-1" to "Tanvir")),
        submit: AuthResult<PaymentSubmittedDto> = AuthResult.Ok(submitted()),
    ) = Fake(
        AuthResult.Ok(seats),
        AuthResult.Ok(FamilyPaymentMethodsDto(listOf(bkash, bank), listOf("bKash"), "Rahima")),
        owed,
        submit,
    )

    private fun model(fake: Fake) = PayViewModel(fake, today = { "2026-11-02" })

    /** Hands out `key-1`, `key-2`, ... so a test can name the key a send carried. */
    private class Keys {
        var issued = 0
            private set

        fun next(): String = "key-${++issued}"
    }

    private fun keyed(fake: Fake, keys: Keys) =
        PayViewModel(fake, today = { "2026-11-02" }, newMutationId = keys::next)

    private suspend fun TestScope.filling(
        model: PayViewModel,
        choice: PayChoice = PayChoice.Method(bkash),
    ): PayUiState.Filling {
        model.load()
        advanceUntilIdle()
        model.choose(choice)
        advanceUntilIdle()
        return assertIs(model.state.value)
    }

    @Test
    fun `send money opens on the methods even with nothing owed`() = runTest(dispatcher) {
        val model = model(fake(owed = AuthResult.Ok(owed("0.00", "e-1" to "Tanvir"))))

        model.load()
        advanceUntilIdle()
        val methods = assertIs<PayUiState.Methods>(model.state.value)
        model.choose(PayChoice.Method(bkash))
        advanceUntilIdle()
        val form = assertIs<PayUiState.Filling>(model.state.value)

        assertEquals(listOf(bkash, bank), methods.scope.methods)
        assertEquals("Rahima", methods.scope.teacherName)
        assertEquals("", form.form.amount)
        assertEquals("2026-11-02", form.form.paidOn)
    }

    @Test
    fun `guardian sees children of the chosen batch only`() = runTest(dispatcher) {
        val model =
            model(
                fake(
                    seats =
                        listOf(
                            seat("e-1", "Physics", "Tanvir"),
                            seat("e-2", "Physics", "Tania"),
                            seat("e-3", "Math", "Tanvir", teacher = "Karim"),
                        ),
                ),
            )

        model.load(preselect = "e-3")
        advanceUntilIdle()
        val math = assertIs<PayUiState.Methods>(model.state.value).scope
        model.chooseBatch(math.batches.first().key)
        advanceUntilIdle()
        val physics = assertIs<PayUiState.Methods>(model.state.value).scope

        assertEquals(listOf("e-3"), math.batch.seats.map { it.enrollmentId })
        assertEquals(listOf("e-3"), math.selected)
        assertEquals(listOf("Tanvir", "Tania"), physics.batch.seats.map { it.childName })
        assertEquals(listOf("e-1", "e-2"), physics.selected)
    }

    @Test
    fun `student for field is fixed to self`() = runTest(dispatcher) {
        val model = model(fake(seats = listOf(seat("e-1", "Physics"), seat("e-2", "Math", teacher = "Karim"))))

        val form = filling(model)

        assertEquals(1, form.scope.batch.seats.size)
        assertNull(form.scope.batch.seats.single().childName)
        model.toggleChild("e-1")
        assertEquals(listOf("e-1"), assertIs<PayUiState.Filling>(model.state.value).scope.selected)
    }

    @Test
    fun `owed line comes from server`() = runTest(dispatcher) {
        val fake =
            fake(
                seats = listOf(seat("e-1", "Physics", "Tanvir"), seat("e-2", "Physics", "Tania")),
                owed = AuthResult.Ok(owed("2000.00", "e-1" to "Tanvir", "e-2" to "Tania")),
            )
        val model = model(fake)

        val form = filling(model)

        assertEquals(listOf(listOf("e-1", "e-2")), fake.owedReads)
        assertEquals(Money.of("2000.00"), form.owed?.owedTogether)
        assertEquals("2000.00", form.form.amount)
    }

    @Test
    fun `dropping a child asks the server again`() = runTest(dispatcher) {
        val fake =
            fake(seats = listOf(seat("e-1", "Physics", "Tanvir"), seat("e-2", "Physics", "Tania")))
        val model = model(fake)
        filling(model)

        model.toggleChild("e-2")
        advanceUntilIdle()
        model.toggleChild("e-1")
        advanceUntilIdle()

        assertEquals(listOf("e-1"), assertIs<PayUiState.Filling>(model.state.value).scope.selected)
        assertEquals(listOf("e-1", "e-2"), fake.owedReads.first())
        assertEquals(listOf("e-1"), fake.owedReads.last())
    }

    @Test
    fun `mobile requires trx and bank requires from account`() = runTest(dispatcher) {
        val fake = fake()
        val model = model(fake)
        val mobile = filling(model)

        model.type(mobile.form.copy(fromAccount = "1234567"))
        model.send()
        advanceUntilIdle()
        model.type(mobile.form.copy(transactionId = "9KD7Q2XL1M", fromAccount = "1234567"))
        model.send()
        advanceUntilIdle()
        val bankModel = model(fake)
        val bankForm = filling(bankModel, PayChoice.Method(bank))
        bankModel.type(bankForm.form.copy(transactionId = "9KD7Q2XL1M"))
        bankModel.send()
        advanceUntilIdle()
        bankModel.type(bankForm.form.copy(fromAccount = "1234 5678"))
        bankModel.send()
        advanceUntilIdle()

        assertEquals(
            listOf(
                PaymentSubmitDto(
                    listOf("e-1"), "m-1", false, Money.of("1000.00"), "2026-11-02", transactionId = "9KD7Q2XL1M",
                ),
                PaymentSubmitDto(
                    listOf("e-1"), "m-2", false, Money.of("1000.00"), "2026-11-02", fromAccount = "1234 5678",
                ),
            ),
            // The replay key is random per attempt and has tests of its
            // own below; this one is about the payment's content.
            fake.sent.map { it.copy(clientMutationId = null) },
        )
    }

    @Test
    fun `a short transaction id is flagged and nothing is sent`() = runTest(dispatcher) {
        val fake = fake()
        val model = model(fake)
        val form = filling(model)

        model.type(form.form.copy(transactionId = "DJ6"))
        model.send()
        advanceUntilIdle()

        assertEquals(FormProblem.TRANSACTION_ID_SHORT, assertIs<PayUiState.Filling>(model.state.value).problem)
        assertEquals(emptyList(), fake.sent)
    }

    @Test
    fun `cash sends no reference and no method`() = runTest(dispatcher) {
        val fake = fake()
        val model = model(fake)
        val form = filling(model, PayChoice.Cash)

        model.type(form.form.copy(note = "  in class  "))
        model.send()
        advanceUntilIdle()

        assertEquals(
            listOf(
                PaymentSubmitDto(listOf("e-1"), null, true, Money.of("1000.00"), "2026-11-02", note = "in class"),
            ),
            fake.sent.map { it.copy(clientMutationId = null) },
        )
        assertIs<PayUiState.Sent>(model.state.value)
    }

    @Test
    fun `send is disabled while sending`() = runTest(dispatcher) {
        val fake = fake().apply { gate = CompletableDeferred() }
        val model = model(fake)
        val form = filling(model)
        model.type(form.form.copy(transactionId = "9KD7Q2XL1M"))

        model.send()
        advanceUntilIdle()
        model.send()
        advanceUntilIdle()

        assertEquals(true, assertIs<PayUiState.Filling>(model.state.value).sending)
        assertEquals(1, fake.sent.size)
        fake.gate?.complete(Unit)
        advanceUntilIdle()
        assertIs<PayUiState.Sent>(model.state.value)
    }

    @Test
    fun `server refusal shows message key and keeps the form`() = runTest(dispatcher) {
        val refused = AuthResult.Refused(ErrorEnvelope(ErrorBody("X", false, "fees.payment.date_in_future")))
        val model = model(fake(submit = refused))
        val form = filling(model)
        val typed = form.form.copy(transactionId = "9KD7Q2XL1M")
        model.type(typed)

        model.send()
        advanceUntilIdle()

        val failed = assertIs<PayUiState.Filling>(model.state.value)
        assertEquals("fees.payment.date_in_future", failed.failedKey)
        assertEquals(typed, failed.form)
        assertEquals(false, failed.sending)
    }

    @Test
    fun `no connection keeps the details and is not queued`() = runTest(dispatcher) {
        val model = model(fake(submit = AuthResult.TransportFailure))
        val form = filling(model)
        model.type(form.form.copy(transactionId = "9KD7Q2XL1M"))

        model.send()
        advanceUntilIdle()

        assertEquals(PayMapper.OFFLINE_KEY, assertIs<PayUiState.Filling>(model.state.value).failedKey)
    }

    @Test
    fun `a sent payment carries the server's record and the reference`() = runTest(dispatcher) {
        val model = model(fake())
        val form = filling(model)
        model.type(form.form.copy(transactionId = "9KD7Q2XL1M"))

        model.send()
        advanceUntilIdle()

        val sent = assertIs<PayUiState.Sent>(model.state.value)
        assertEquals("9KD7Q2XL1M", sent.reference)
        assertEquals("Rahima", sent.teacherName)
        assertEquals("Physics", sent.batchName)
        assertEquals(Money.of("1000.00"), sent.payment.totalAmount)
    }

    @Test
    fun `changing batch keeps a method the new teacher also offers`() = runTest(dispatcher) {
        val model =
            model(
                fake(
                    seats = listOf(seat("e-1", "Physics"), seat("e-2", "Math", teacher = "Karim")),
                ),
            )
        filling(model)
        val other = assertIs<PayUiState.Filling>(model.state.value).scope.batches.last().key

        model.chooseBatch(other)
        advanceUntilIdle()

        val kept = assertIs<PayUiState.Filling>(model.state.value)
        assertEquals("e-2", kept.scope.batch.seats.single().enrollmentId)
    }

    @Test
    fun `no accepted seat is the empty state and a failed read can be retried`() = runTest(dispatcher) {
        val fake = fake(seats = emptyList())
        val model = model(fake)

        model.load()
        advanceUntilIdle()
        assertEquals(PayUiState.NoSeats, model.state.value)

        fake.seats = AuthResult.TransportFailure
        model.load()
        advanceUntilIdle()

        assertEquals(PayUiState.Failed(PayMapper.OFFLINE_KEY, true), model.state.value)
    }

    // ------------------------------------------------------------------
    // The payment replay key [PA-DB-1, FE-5]. A send can time out after
    // the server recorded it; without a key, the payer's second tap made
    // a second pending claim for the same money.
    // ------------------------------------------------------------------

    @Test
    fun `every payment is sent with a replay key`() = runTest(dispatcher) {
        val fake = fake()
        val model = keyed(fake, Keys())
        val form = filling(model)
        model.type(form.form.copy(transactionId = "9KD7Q2XL1M"))

        model.send()
        advanceUntilIdle()

        assertEquals(listOf<String?>("key-1"), fake.sent.map { it.clientMutationId })
    }

    @Test
    fun `sending the same payment again after a lost response reuses its key`() = runTest(dispatcher) {
        // The first send reached the server and the answer was lost.
        // The retry must carry the SAME key, so the server returns the
        // submission it already holds instead of recording another. That
        // replay comes back as an ordinary success.
        val fake = fake(submit = AuthResult.TransportFailure)
        val keys = Keys()
        val model = keyed(fake, keys)
        val form = filling(model)
        model.type(form.form.copy(transactionId = "9KD7Q2XL1M"))
        model.send()
        advanceUntilIdle()

        fake.submit = AuthResult.Ok(submitted())
        model.send()
        advanceUntilIdle()

        assertEquals(listOf<String?>("key-1", "key-1"), fake.sent.map { it.clientMutationId })
        assertEquals(1, keys.issued)
        assertIs<PayUiState.Sent>(model.state.value)
    }

    @Test
    fun `a refused payment sent again unchanged keeps its key`() = runTest(dispatcher) {
        val refused = AuthResult.Refused(ErrorEnvelope(ErrorBody("X", true, "error.server")))
        val fake = fake(submit = refused)
        val model = keyed(fake, Keys())
        val form = filling(model)
        model.type(form.form.copy(transactionId = "9KD7Q2XL1M"))

        model.send()
        advanceUntilIdle()
        model.send()
        advanceUntilIdle()

        assertEquals(listOf<String?>("key-1", "key-1"), fake.sent.map { it.clientMutationId })
    }

    @Test
    fun `an edited payment is a new attempt with a new key`() = runTest(dispatcher) {
        // Changing what was paid makes it a different payment. Reusing
        // the key would have the server answer with the OLD submission
        // and drop the correction.
        val fake = fake(submit = AuthResult.TransportFailure)
        val model = keyed(fake, Keys())
        val form = filling(model)
        model.type(form.form.copy(transactionId = "9KD7Q2XL1M"))
        model.send()
        advanceUntilIdle()

        model.type(form.form.copy(transactionId = "9KD7Q2XL1M", amount = "900.00"))
        model.send()
        advanceUntilIdle()

        assertEquals(listOf<String?>("key-1", "key-2"), fake.sent.map { it.clientMutationId })
    }

    @Test
    fun `the next payment after a successful one gets a new key`() = runTest(dispatcher) {
        // Two genuine payments of the same amount on the same day are two
        // payments. Only a retry of one attempt may share its key.
        val fake = fake()
        val model = keyed(fake, Keys())
        val first = filling(model)
        model.type(first.form.copy(transactionId = "9KD7Q2XL1M"))
        model.send()
        advanceUntilIdle()
        assertIs<PayUiState.Sent>(model.state.value)

        val second = filling(model)
        model.type(second.form.copy(transactionId = "9KD7Q2XL1M"))
        model.send()
        advanceUntilIdle()

        assertEquals(listOf<String?>("key-1", "key-2"), fake.sent.map { it.clientMutationId })
    }
}
