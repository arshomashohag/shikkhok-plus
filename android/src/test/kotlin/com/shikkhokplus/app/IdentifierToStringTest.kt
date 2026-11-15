package com.shikkhokplus.app

import com.shikkhokplus.app.core.model.EmailEdit
import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.core.model.IdentifierKind
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.model.PostalAddress
import com.shikkhokplus.app.core.model.SignupRole
import com.shikkhokplus.app.core.network.ContactChangeRequest
import com.shikkhokplus.app.core.network.ContactRemoveRequest
import com.shikkhokplus.app.core.network.IssueRequest
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.core.network.MemberDto
import com.shikkhokplus.app.core.network.MemberInviteDto
import com.shikkhokplus.app.core.network.PasswordSignInRequest
import com.shikkhokplus.app.core.network.RosterRowDto
import com.shikkhokplus.app.core.network.SignupRequestDto
import com.shikkhokplus.app.core.network.StudentCreateBody
import com.shikkhokplus.app.core.network.StudentUpdateBody
import com.shikkhokplus.app.core.network.TeacherStudentDto
import com.shikkhokplus.app.core.network.UsernameAvailabilityRequest
import com.shikkhokplus.app.core.network.UsernameChangeDto
import com.shikkhokplus.app.core.network.UsernameChangeRequest
import com.shikkhokplus.app.core.network.VerifyRequest
import com.shikkhokplus.app.feature.account.ContactCard
import com.shikkhokplus.app.feature.account.ContactsUiState
import com.shikkhokplus.app.feature.account.RemoveContactUiState
import com.shikkhokplus.app.feature.account.UsernameUiState
import com.shikkhokplus.app.feature.auth.AuthUiState
import com.shikkhokplus.app.feature.auth.SignupForm
import com.shikkhokplus.app.feature.centres.MemberLine
import com.shikkhokplus.app.feature.centres.MembersUiState
import com.shikkhokplus.app.feature.profile.ProfileSummary
import com.shikkhokplus.app.feature.profile.ProfileUiState
import com.shikkhokplus.app.feature.profile.ui.MoreActions
import com.shikkhokplus.app.feature.roster.RosterRow
import com.shikkhokplus.app.core.model.LinkState
import com.shikkhokplus.app.feature.students.StudentDetail
import com.shikkhokplus.app.feature.students.StudentListRow
import com.shikkhokplus.app.feature.students.ui.NewStudent
import com.shikkhokplus.app.navigation.AccountRows
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * No class this unit adds or changes prints an identifier [U3: NFR3.2].
 *
 * A Kotlin data class prints every property, so a username, a contact or
 * a password in one reaches any crash report, assertion message or log
 * that prints the object. Two halves:
 *
 * - **Structural**: over an explicit list of the files this unit adds or
 *   changes, every `data class` declaring a property named EXACTLY one of
 *   [IDENTIFYING] must declare `override fun toString`. Exact names, never
 *   `value` or `code` (a property called `code` is an error code far more
 *   often than a one-time code, and would drown the list in exemptions).
 *   A new class with such a property cannot slip past without this going
 *   red.
 * - **Behavioural**: one instance of each such class, built with the
 *   sentinels the test instructions name, and its `toString()` checked for
 *   none of them, so an override that exists but does not mask fails.
 *
 * **Stated limit:** the structural half is textual (no type resolution),
 * like `NoFloatingPointTest`; it reads constructor properties only.
 */
class IdentifierToStringTest {

    private val root = File("src/main/kotlin/com/shikkhokplus/app")

    /** The files this unit adds or changes that declare data classes. */
    private val files =
        listOf(
            "core/model/Identifier.kt",
            "core/model/EmailEdit.kt",
            "core/network/AuthDto.kt",
            "core/network/AccountsDto.kt",
            "core/network/UsernameDto.kt",
            "core/network/ProfileDto.kt",
            "core/network/CentreDto.kt",
            "core/network/TeacherStudentDto.kt",
            "core/network/RosterDto.kt",
            "feature/auth/AuthUiState.kt",
            "feature/auth/SignupStateMapper.kt",
            "feature/account/ChooseUsername.kt",
            "feature/account/Username.kt",
            "feature/account/Contacts.kt",
            "feature/account/ReplaceContact.kt",
            "feature/account/RemoveContact.kt",
            "feature/students/StudentsUiState.kt",
            "feature/students/ui/AddStudentForm.kt",
            "feature/roster/RosterUiState.kt",
            "feature/centres/CentresViewModels.kt",
            "feature/profile/ProfileUiState.kt",
            "feature/profile/ui/ProfileScreen.kt",
            "navigation/AccountRoutes.kt",
        )

    /** A data class's name, its constructor, and the text after it up to the next declaration. */
    private data class Declared(val file: String, val name: String, val properties: Set<String>, val body: String)

    private fun declarations(file: File): List<Declared> {
        val text = file.readText()
        return Regex("""\bdata class (\w+)\s*\(""").findAll(text).map { match ->
            val open = match.range.last
            var depth = 0
            var close = open
            for (i in open until text.length) {
                if (text[i] == '(') depth++
                if (text[i] == ')') depth--
                if (depth == 0) {
                    close = i
                    break
                }
            }
            val params = text.substring(open, close)
            val properties = Regex("""\b(?:val|var)\s+(\w+)\s*:""").findAll(params).map { it.groupValues[1] }.toSet()
            Declared(file.name, match.groupValues[1], properties, bodyAfter(text, close))
        }.toList()
    }

    /** The class body following a constructor, or "" when it has none. */
    private fun bodyAfter(text: String, close: Int): String {
        val header = text.substring(close + 1).substringBefore("\n\n").substringBefore("\n/**")
        val brace = header.indexOf('{')
        if (brace < 0) return ""
        val start = close + 1 + brace
        var depth = 0
        for (i in start until text.length) {
            if (text[i] == '{') depth++
            if (text[i] == '}') depth--
            if (depth == 0) return text.substring(start, i + 1)
        }
        return text.substring(start)
    }

    @Test
    fun `every data class here with an identifying property overrides toString`() {
        val declared = files.flatMap { declarations(File(root, it)) }
        assertTrue(declared.size > 30, "the declarations were not found; this test would pass vacuously")

        val unmasked =
            declared
                .filter { it.properties.any(IDENTIFYING::contains) }
                .filterNot { "override fun toString" in it.body }
                .map { "${it.file}: ${it.name} ${it.properties.filter(IDENTIFYING::contains)}" }

        assertEquals(emptyList(), unmasked)
    }

    @Test
    fun `the structural scan finds the classes it is meant to`() {
        val names = files.flatMap { declarations(File(root, it)) }.filter { it.properties.any(IDENTIFYING::contains) }
            .map { it.name }
            .toSet()

        listOf("SignupForm", "VerifyRequest", "ContactCard", "MemberLine", "StudentDetail", "MeDto").forEach {
            assertTrue(it in names, "$it was not seen by the scan")
        }
    }

    @Test
    fun `no instance prints a sentinel`() {
        val instances = wireInstances() + stateInstances()
        assertTrue(instances.size > 35, "the instance list was emptied; this test would pass vacuously")

        instances.forEach { instance ->
            val text = instance.toString()
            listOf(USER, EMAIL, PHONE, PASS).forEach { sentinel ->
                assertFalse(sentinel in text, "${instance::class.simpleName} printed $sentinel: $text")
            }
        }
    }

    /** Request and response bodies, each holding every sentinel it can. */
    private fun wireInstances(): List<Any> =
        listOf(
            Identifier.email(EMAIL),
            EmailEdit.Set(EMAIL),
            IssueRequest(phone = PHONE),
            VerifyRequest(email = EMAIL, code = "123456", username = USER),
            PasswordSignInRequest(password = PASS, login = USER),
            SignupRequestDto(
                phone = PHONE,
                role = "student",
                selfName = "R",
                addressHouse = "1",
                addressRoad = "2",
                addressCity = "D",
                addressPostcode = "1205",
                username = USER,
            ),
            UsernameAvailabilityRequest(USER),
            UsernameChangeRequest(USER, PASS),
            UsernameChangeDto(USER, null),
            ContactChangeRequest(email = EMAIL, password = PASS),
            ContactRemoveRequest("phone", PASS),
            MeDto(username = USER, phone = PHONE, email = EMAIL),
            MemberDto("m", "R", PHONE, "teacher", "pending", invitedEmail = EMAIL),
            MemberInviteDto("R", PHONE, "teacher", EMAIL),
            TeacherStudentDto(
                studentId = "s",
                displayName = "R",
                studentPhone = PHONE,
                guardianPhone = PHONE,
                studentState = "pending",
                guardianState = "absent",
                totalOutstanding = Money.of("0.00"),
                isRemovable = true,
                studentEmail = EMAIL,
                guardianEmail = EMAIL,
            ),
            StudentCreateBody("R", PHONE, PHONE, studentEmail = EMAIL, guardianEmail = EMAIL),
            StudentUpdateBody(studentPhone = PHONE, guardianPhone = PHONE, studentEmail = EmailEdit.Set(EMAIL)),
            RosterRowDto(
                enrollmentId = "e",
                displayName = "R",
                guardianPhone = PHONE,
                status = "active",
                studentState = "pending",
                guardianState = "pending",
                isRemovable = true,
                studentEmail = EMAIL,
                guardianEmail = EMAIL,
            ),
        )

    /** UI states and view models' rows, each holding every sentinel it can. */
    private fun stateInstances(): List<Any> =
        listOf(
            AuthUiState.ReplaceUsername(USER),
            SignupForm(Identifier.email(EMAIL), "R", PostalAddress(), SignupRole.STUDENT, PASS, PASS, null, USER),
            UsernameUiState.Viewing(USER),
            UsernameUiState.Editing(USER),
            UsernameUiState.Changed(USER, null),
            ContactCard(IdentifierKind.EMAIL, EMAIL),
            ContactsUiState.Loaded(
                ContactCard(IdentifierKind.PHONE, PHONE),
                ContactCard(IdentifierKind.EMAIL, EMAIL),
                false,
            ),
            RemoveContactUiState.Confirming(IdentifierKind.EMAIL, EMAIL),
            MembersUiState(invitePhone = PHONE, inviteEmail = EMAIL),
            MemberLine("m", "R", EMAIL, "teacher", "pending", false, false),
            StudentListRow("s", "R", EMAIL, emptyList()),
            StudentDetail(
                "s", "R", PHONE, PHONE, "pending", "absent", emptyList(), Money.of("0.00"), true, emptyList(),
                EMAIL, EMAIL, PHONE, EMAIL,
            ),
            NewStudent("R", PHONE, PHONE, emptyList(), EMAIL, EMAIL),
            RosterRow("e", "R", "k", null, PHONE, LinkState.PENDING, LinkState.ABSENT, "R", false, true, EMAIL),
            ProfileSummary(null, null, PHONE, email = EMAIL, username = USER),
            ProfileUiState.Viewing(null, null, PHONE),
            ProfileUiState.Saved(null, null, PHONE),
            MoreActions(username = USER, contactsLine = EMAIL),
            AccountRows({}, true, {}, USER, {}, EMAIL),
        )

    private companion object {
        val IDENTIFYING =
            setOf(
                "username", "login", "previous", "phone", "email", "password", "currentPassword", "newPassword",
                "confirm", "invitePhone", "inviteEmail", "invitedEmail", "studentPhone", "guardianPhone",
                "studentEmail", "guardianEmail", "contact", "contactLine", "studentContactLine", "guardianContactLine",
            )

        const val USER = "sentinel_user_7"
        const val EMAIL = "sentinel@example.invalid"
        const val PHONE = "+8801999999999"
        const val PASS = "sentinel-pass"
    }
}
