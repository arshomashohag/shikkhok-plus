package com.shikkhokplus.app.feature.centres

import com.shikkhokplus.app.core.network.CentreDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.MemberDto
import com.shikkhokplus.app.core.network.MembershipDecisionDto
import com.shikkhokplus.app.core.network.MembershipDto
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

/** Opening a centre, its members, and centres' offers. */
@OptIn(ExperimentalCoroutinesApi::class)
class CentresViewModelsTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private class Fake : CentresRepository {
        var openResult: AuthResult<CentreDto> = AuthResult.Ok(CentreDto("w-centre", "Udayan Coaching"))
        var membersResult: AuthResult<List<MemberDto>> = AuthResult.Ok(listOf(member("m-me", isYou = true)))
        var inviteResult: AuthResult<MemberDto> = AuthResult.Ok(member("m-new", name = "Karim"))
        var revokeResult: AuthResult<Unit> = AuthResult.Ok(Unit)
        var offersResult: AuthResult<List<MembershipDto>> = AuthResult.Ok(emptyList())
        var decisionResult: AuthResult<MembershipDecisionDto> = AuthResult.Ok(MembershipDecisionDto("o-1", "accepted"))
        val opened = mutableListOf<Pair<String, String>>()
        /** Each invitation: name, phone, email, role. */
        val invited = mutableListOf<List<String?>>()
        val revoked = mutableListOf<String>()
        val decided = mutableListOf<Pair<String, Boolean>>()
        var memberReads = 0

        override suspend fun open(name: String, managerName: String): AuthResult<CentreDto> {
            opened += name to managerName
            return openResult
        }

        override suspend fun members(): AuthResult<List<MemberDto>> {
            memberReads++
            return membersResult
        }

        override suspend fun invite(
            displayName: String,
            phone: String?,
            email: String?,
            role: String,
        ): AuthResult<MemberDto> {
            invited += listOf(displayName, phone, email, role)
            return inviteResult
        }

        override suspend fun revoke(memberId: String): AuthResult<Unit> {
            revoked += memberId
            return revokeResult
        }

        override suspend fun offers(): AuthResult<List<MembershipDto>> = offersResult

        override suspend fun accept(memberId: String): AuthResult<MembershipDecisionDto> {
            decided += memberId to true
            return decisionResult
        }

        override suspend fun decline(memberId: String): AuthResult<MembershipDecisionDto> {
            decided += memberId to false
            return decisionResult
        }

        companion object {
            fun member(
                id: String,
                name: String = "Rahima",
                role: String = "manager",
                decision: String = "accepted",
                isYou: Boolean = false,
            ) = MemberDto(id, name, "+8801711000000", role, decision, revoked = false, isYou = isYou)
        }
    }

    private fun refusal(key: String) = AuthResult.Refused(ErrorEnvelope(ErrorBody("X", false, key)))

    // ------------------------------------------------------------ open

    @Test
    fun `a centre opens once both names are given, trimmed`() = runTest(dispatcher) {
        val fake = Fake()
        val model = OpenCentreViewModel(fake, managerName = "Rahima")
        assertFalse(model.state.value.canOpen)

        model.name("  Udayan Coaching ")
        assertTrue(model.state.value.canOpen)
        model.open()
        advanceUntilIdle()

        assertEquals(listOf("Udayan Coaching" to "Rahima"), fake.opened)
        assertEquals("w-centre", model.state.value.opened?.ownerId)
        assertFalse(model.state.value.canOpen, "an opened centre is not opened twice")
    }

    @Test
    fun `a refused or offline open says why and keeps the form`() = runTest(dispatcher) {
        val fake = Fake()
        fake.openResult = refusal("centre.name_required")
        val model = OpenCentreViewModel(fake)
        model.name("Udayan")
        model.managerName("Rahima")
        model.open()
        advanceUntilIdle()
        assertEquals("centre.name_required", model.state.value.failureKey)
        assertNull(model.state.value.opened)

        fake.openResult = AuthResult.TransportFailure
        model.open()
        advanceUntilIdle()
        assertEquals("error.network.unreachable", model.state.value.failureKey)
        assertEquals("Udayan", model.state.value.name)
    }

    // --------------------------------------------------------- members

    @Test
    fun `inviting sends the form, reads the list again and clears the form`() = runTest(dispatcher) {
        val fake = Fake()
        val model = MembersViewModel(fake)
        model.load()
        advanceUntilIdle()

        model.inviteName(" Karim ")
        model.invitePhone("01811 223344")
        model.inviteRole(MemberRole.MANAGER)
        model.invite()
        advanceUntilIdle()

        assertEquals(listOf(listOf("Karim", "01811 223344", null, "manager")), fake.invited)
        assertEquals(2, fake.memberReads)
        val state = model.state.value
        assertEquals("Karim", state.invited)
        assertEquals("", state.inviteName)
        assertEquals(MemberRole.TEACHER, state.inviteRole)
    }

    @Test
    fun `a refused invitation keeps what was typed`() = runTest(dispatcher) {
        val fake = Fake()
        fake.inviteResult = refusal("centre.member.already_invited")
        val model = MembersViewModel(fake)
        model.inviteName("Karim")
        model.invitePhone("01811223344")
        model.invite()
        advanceUntilIdle()

        assertEquals("centre.member.already_invited", model.state.value.failureKey)
        assertEquals("Karim", model.state.value.inviteName)
        assertFalse(model.state.value.inviting)
    }

    @Test
    fun `an invitation needs a name and a phone`() {
        val model = MembersViewModel(Fake())
        model.inviteName("Karim")
        assertFalse(model.state.value.canInvite)
        model.invitePhone("018")
        assertTrue(model.state.value.canInvite, "the server checks the number, not the form")
    }

    // --- U3: invite by phone or email, members without a phone [FR6.4, W8] --

    @Test
    fun `an invitation needs a name and a phone or an email, never neither`() {
        val model = MembersViewModel(Fake())
        model.inviteName("Rina")
        assertFalse(model.state.value.canInvite, "neither contact")
        model.inviteEmail("rina@example.com")
        assertTrue(model.state.value.canInvite, "email only")
        model.inviteEmail("")
        model.invitePhone("01811223344")
        assertTrue(model.state.value.canInvite, "phone only")
    }

    @Test
    fun `an email-only invitation sends the email and leaves the phone out`() = runTest(dispatcher) {
        val fake = Fake()
        val model = MembersViewModel(fake)
        model.inviteName("Rina")
        model.inviteEmail(" rina@example.com ")
        model.invite()
        advanceUntilIdle()

        assertEquals(listOf(listOf("Rina", null, "rina@example.com", "teacher")), fake.invited)
    }

    @Test
    fun `a malformed email is named on the form and nothing is sent`() = runTest(dispatcher) {
        val fake = Fake()
        val model = MembersViewModel(fake)
        model.inviteName("Rina")
        model.inviteEmail("rina@example")
        model.invite()
        advanceUntilIdle()

        assertTrue(model.state.value.inviteEmailRejected)
        assertEquals(emptyList(), fake.invited)

        model.inviteEmail("rina@example.com")
        assertFalse(model.state.value.inviteEmailRejected, "an edit clears the refusal")
    }

    @Test
    fun `an already-invited contact is said as a banner and the form is kept`() = runTest(dispatcher) {
        val fake = Fake()
        fake.inviteResult = refusal("centre.member.already_invited")
        val model = MembersViewModel(fake)
        model.inviteName("Rina")
        model.inviteEmail("rina@example.com")
        model.invite()
        advanceUntilIdle()

        assertEquals("centre.member.already_invited", model.state.value.failureKey)
        assertEquals("rina@example.com", model.state.value.inviteEmail)
    }

    @Test
    fun `a member's contact line is the phone, else the invited email`() {
        val byPhone = MemberDto("m1", "Karim", "+8801712345678", "teacher", "accepted")
        val byEmail = MemberDto("m2", "Rina", null, "teacher", "pending", invitedEmail = "rina@example.com")
        val both = byPhone.copy(invitedEmail = "karim@example.com")

        assertEquals("01712-345678", MemberLine.of(byPhone).contactLine)
        assertEquals("rina@example.com", MemberLine.of(byEmail).contactLine)
        assertEquals("01712-345678", MemberLine.of(both).contactLine)
        assertEquals(null, MemberLine.of(byEmail.copy(invitedEmail = null)).contactLine)
    }

    @Test
    fun `the list maps to lines and an email-only member loads`() = runTest(dispatcher) {
        val fake = Fake()
        fake.membersResult =
            AuthResult.Ok(
                listOf(MemberDto("m2", "Rina", null, "teacher", "pending", invitedEmail = "rina@example.com")),
            )
        val model = MembersViewModel(fake)
        model.load()
        advanceUntilIdle()

        val loaded = assertIs<MembersBody.Loaded>(model.state.value.body)
        assertEquals("rina@example.com", loaded.members.single().contactLine)
    }

    @Test
    fun `the members state and lines never print a contact`() {
        val state = MembersUiState(invitePhone = "+8801999999999", inviteEmail = "sentinel@example.invalid")
        val line = MemberLine("m", "Rina", "sentinel@example.invalid", "teacher", "pending", false, false)

        listOf(state.toString(), line.toString()).forEach { printed ->
            assertFalse("+8801999999999" in printed || "sentinel@example.invalid" in printed, printed)
        }
    }

    @Test
    fun `removing reads the list again, and removing the last manager is refused`() = runTest(dispatcher) {
        val fake = Fake()
        val model = MembersViewModel(fake)
        model.load()
        advanceUntilIdle()

        model.revoke("m-2")
        advanceUntilIdle()
        assertEquals(listOf("m-2"), fake.revoked)
        assertEquals(2, fake.memberReads)

        fake.revokeResult = refusal("centre.member.last_manager")
        model.revoke("m-me")
        advanceUntilIdle()
        assertEquals("centre.member.last_manager", model.state.value.failureKey)
    }

    @Test
    fun `an offline member list can be retried`() = runTest(dispatcher) {
        val fake = Fake()
        fake.membersResult = AuthResult.TransportFailure
        val model = MembersViewModel(fake)
        model.load()
        advanceUntilIdle()
        assertEquals(MembersBody.Failed("error.network.unreachable", true), model.state.value.body)

        fake.membersResult = AuthResult.Ok(emptyList())
        model.retry()
        advanceUntilIdle()
        assertIs<MembersBody.Loaded>(model.state.value.body)
    }

    // ---------------------------------------------------------- offers

    private fun offer(id: String, decision: String = "pending") =
        MembershipDto(id, "Udayan Coaching", "teacher", decision)

    @Test
    fun `only pending offers are listed, and accepting one is reported`() = runTest(dispatcher) {
        val fake = Fake()
        fake.offersResult = AuthResult.Ok(listOf(offer("o-1"), offer("o-2", decision = "declined")))
        val model = CentreOffersViewModel(fake)
        model.load()
        advanceUntilIdle()
        assertEquals(listOf("o-1"), model.state.value.offers.map { it.memberId })

        model.accept("o-1")
        advanceUntilIdle()

        assertEquals(listOf("o-1" to true), fake.decided)
        assertTrue(model.state.value.offers.isEmpty())
        assertEquals(1, model.state.value.accepted)
    }

    @Test
    fun `declining removes the offer without reporting an acceptance`() = runTest(dispatcher) {
        val fake = Fake()
        fake.offersResult = AuthResult.Ok(listOf(offer("o-1")))
        val model = CentreOffersViewModel(fake)
        model.load()
        advanceUntilIdle()

        model.decline("o-1")
        advanceUntilIdle()

        assertEquals(listOf("o-1" to false), fake.decided)
        assertEquals(0, model.state.value.accepted)
    }

    @Test
    fun `a refused answer keeps the offer and says why, and an unknown offer is ignored`() = runTest(dispatcher) {
        val fake = Fake()
        fake.offersResult = AuthResult.Ok(listOf(offer("o-1")))
        fake.decisionResult = refusal("centre.member.already_revoked")
        val model = CentreOffersViewModel(fake)
        model.load()
        advanceUntilIdle()

        model.accept("o-unknown")
        model.accept("o-1")
        advanceUntilIdle()

        assertEquals(listOf("o-1" to true), fake.decided)
        assertEquals("centre.member.already_revoked", model.state.value.failureKey)
        assertEquals(listOf("o-1"), model.state.value.offers.map { it.memberId })
    }

    @Test
    fun `a failed offers read shows no offers rather than failing the screen`() = runTest(dispatcher) {
        val fake = Fake()
        fake.offersResult = AuthResult.TransportFailure
        val model = CentreOffersViewModel(fake)
        model.load()
        advanceUntilIdle()

        assertTrue(model.state.value.offers.isEmpty())
        assertNull(model.state.value.failureKey)
    }
}
