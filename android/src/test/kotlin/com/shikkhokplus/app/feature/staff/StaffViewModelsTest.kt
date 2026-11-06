package com.shikkhokplus.app.feature.staff

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.model.PostalAddress
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.StaffBodyDto
import com.shikkhokplus.app.core.network.StaffDto
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
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** The Teachers & staff console: its list, marking as left, and the form. */
@OptIn(ExperimentalCoroutinesApi::class)
class StaffViewModelsTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private class Fake : StaffRepository {
        var listResult: AuthResult<List<StaffDto>> = AuthResult.Ok(listOf(teacher()))
        var writeResult: AuthResult<StaffDto> = AuthResult.Ok(teacher())
        val invited = mutableListOf<StaffBodyDto>()
        val added = mutableListOf<StaffBodyDto>()
        val updated = mutableListOf<Pair<String, StaffBodyDto>>()
        val left = mutableListOf<String>()
        var reads = 0

        override suspend fun list(): AuthResult<List<StaffDto>> {
            reads++
            return listResult
        }

        override suspend fun inviteTeacher(body: StaffBodyDto): AuthResult<StaffDto> {
            invited += body
            return writeResult
        }

        override suspend fun addOther(body: StaffBodyDto): AuthResult<StaffDto> {
            added += body
            return writeResult
        }

        override suspend fun update(staffId: String, body: StaffBodyDto): AuthResult<StaffDto> {
            updated += staffId to body
            return writeResult
        }

        override suspend fun leave(staffId: String, leftOn: String?): AuthResult<StaffDto> {
            left += staffId
            return writeResult
        }
    }

    private fun refusal(key: String) = AuthResult.Refused(ErrorEnvelope(ErrorBody("X", false, key)))

    // ------------------------------------------------------------ list

    @Test
    fun `the list shows the server's records and can be retried after a failure`() = runTest(dispatcher) {
        val fake = Fake()
        fake.listResult = AuthResult.TransportFailure
        val model = StaffListViewModel(fake)
        model.load()
        advanceUntilIdle()
        assertEquals(StaffListUiState.Failed("error.network.unreachable", true), model.state.value)

        fake.listResult = AuthResult.Ok(listOf(teacher()))
        model.retry()
        advanceUntilIdle()
        assertEquals(listOf("s-1"), assertIs<StaffListUiState.Loaded>(model.state.value).staff.map { it.staffId })
        assertEquals("Karim", model.recordFor("s-1")?.displayName)
    }

    @Test
    fun `marking someone as left reads the list again and says who`() = runTest(dispatcher) {
        val fake = Fake()
        val model = StaffListViewModel(fake)
        model.load()
        advanceUntilIdle()

        model.leave("s-1")
        advanceUntilIdle()

        assertEquals(listOf("s-1"), fake.left)
        assertEquals(2, fake.reads)
        assertEquals("Karim", assertIs<StaffListUiState.Loaded>(model.state.value).notice)
    }

    @Test
    fun `a refused leave keeps the list and says why`() = runTest(dispatcher) {
        val fake = Fake()
        fake.writeResult = refusal("staff.already_left")
        val model = StaffListViewModel(fake)
        model.load()
        advanceUntilIdle()

        model.leave("s-1")
        advanceUntilIdle()

        val loaded = assertIs<StaffListUiState.Loaded>(model.state.value)
        assertEquals("staff.already_left", loaded.failureKey)
        assertEquals(1, loaded.staff.size)
    }

    // ------------------------------------------------------------ form

    @Test
    fun `a teacher needs a name and a number, and a paid basis an amount that parses`() {
        val model = StaffFormViewModel(Fake(), StaffFormMode.InviteTeacher)
        model.name("Karim")
        assertFalse(model.state.value.canSave)
        model.phone("01811223344")
        assertFalse(model.state.value.canSave, "a monthly salary needs its amount")
        model.rate("৮০০০")
        assertTrue(model.state.value.canSave)
        model.basis(PayBasis.NONE)
        assertTrue(model.state.value.canSave)
        assertEquals("", model.state.value.typedRate, "not paid clears the amount")
    }

    @Test
    fun `inviting a teacher sends their details and no role`() = runTest(dispatcher) {
        val fake = Fake()
        val model = StaffFormViewModel(fake, StaffFormMode.InviteTeacher)
        model.name(" Karim ")
        model.phone(" 01811223344 ")
        model.email("  ")
        model.roleLabel("Should not be sent")
        model.address(PostalAddress(house = "12", road = "", city = "Dhaka", postcode = "১২০৫"))
        model.basis(PayBasis.PER_CLASS)
        model.rate("500")
        model.joinedOn("2026-11-01")

        model.save()
        advanceUntilIdle()

        val sent = fake.invited.single()
        assertEquals("Karim", sent.displayName)
        assertEquals("01811223344", sent.phone)
        assertNull(sent.email)
        assertNull(sent.roleLabel)
        assertEquals("12", sent.staffHouse)
        assertNull(sent.staffRoad)
        assertEquals("1205", sent.staffPostcode)
        assertEquals("per_class", sent.payBasis)
        assertEquals(Money.of("500.00"), sent.payRate)
        assertEquals("2026-11-01", sent.joinedOn)
        assertEquals("s-1", model.state.value.saved?.staffId)
    }

    @Test
    fun `other staff may have no number and do have a role`() = runTest(dispatcher) {
        val fake = Fake()
        val model = StaffFormViewModel(fake, StaffFormMode.AddOther)
        model.name("Salma")
        model.roleLabel("Office")
        model.basis(PayBasis.NONE)
        assertTrue(model.state.value.canSave)

        model.save()
        advanceUntilIdle()

        val sent = fake.added.single()
        assertNull(sent.phone)
        assertEquals("Office", sent.roleLabel)
        assertNull(sent.payRate)
        assertNull(sent.joinedOn, "a blank date is today, the server's default")
    }

    @Test
    fun `editing starts from the record and never sends the number`() = runTest(dispatcher) {
        val fake = Fake()
        val model = StaffFormViewModel(fake, StaffFormMode.Edit(teacher()))
        val form = model.state.value
        assertEquals("Karim", form.name)
        assertEquals(PayBasis.MONTHLY, form.basis)
        assertEquals("8000.00", form.typedRate)
        assertEquals("2026-01-01", form.joinedOn)

        model.rate("9000")
        model.save()
        advanceUntilIdle()

        val (id, sent) = fake.updated.single()
        assertEquals("s-1", id)
        assertNull(sent.phone)
        assertEquals(Money.of("9000.00"), sent.payRate)
    }

    @Test
    fun `a refused save keeps what was typed and says why`() = runTest(dispatcher) {
        val fake = Fake()
        fake.writeResult = refusal("staff.pay.rate_required")
        val model = StaffFormViewModel(fake, StaffFormMode.AddOther)
        model.name("Salma")
        model.rate("0")
        model.save()
        advanceUntilIdle()

        assertEquals("staff.pay.rate_required", model.state.value.failureKey)
        assertEquals("Salma", model.state.value.name)
        assertNull(model.state.value.saved)
    }

    companion object {
        fun teacher() =
            StaffDto(
                staffId = "s-1",
                kind = "teacher",
                displayName = "Karim",
                phone = "+8801811223344",
                payBasis = "monthly",
                payRate = Money.of("8000.00"),
                joinedOn = "2026-01-01",
                status = "active",
                access = "invited",
            )
    }
}
