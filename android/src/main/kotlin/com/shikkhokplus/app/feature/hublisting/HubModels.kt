package com.shikkhokplus.app.feature.hublisting

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One requirement of a listing and whether the server counts it met.
 *
 * The client never decides completeness: it draws these as they arrive.
 *
 * @property key The requirement's stable name
 * @property done Whether it is met
 */
@Serializable
data class HubChecklistItem(
    @SerialName("key") val key: String,
    @SerialName("done") val done: Boolean,
)

/**
 * The owner's public listing, as `GET /v1/hub/listing` answers it.
 *
 * @property status `draft`, `published`, `hidden` or `suspended`
 * @property slug The public path segment, or null while a draft
 * @property publicName The name shown publicly
 * @property headlineEn The English headline
 * @property headlineBn The Bangla headline
 * @property bioEn The English biography
 * @property bioBn The Bangla biography
 * @property qualifications Qualifications
 * @property teachingMode How the owner teaches, as wire values
 * @property districtCode The district's BBS code
 * @property upazilaCode The upazila's BBS code
 * @property streetAddress A centre's street address
 * @property publicContactPhone The one number shown publicly
 * @property consentVersion The consent text the owner last agreed to
 * @property publishedAt When it was last published
 * @property checklist Each requirement and whether it is met
 * @property publishable Whether every requirement is met, decided by the server
 * @property runsClasses Whether the owner earns the Runs classes badge
 * @property consentVersionCurrent The consent text version to agree to now
 * @property isCentre Whether the owner is a coaching centre
 */
@Serializable
data class OwnerListingResponse(
    @SerialName("status") val status: String,
    @SerialName("slug") val slug: String? = null,
    @SerialName("public_name") val publicName: String,
    @SerialName("headline_en") val headlineEn: String? = null,
    @SerialName("headline_bn") val headlineBn: String? = null,
    @SerialName("bio_en") val bioEn: String? = null,
    @SerialName("bio_bn") val bioBn: String? = null,
    @SerialName("qualifications") val qualifications: String? = null,
    @SerialName("teaching_mode") val teachingMode: List<String> = emptyList(),
    @SerialName("district_code") val districtCode: String? = null,
    @SerialName("upazila_code") val upazilaCode: String? = null,
    @SerialName("street_address") val streetAddress: String? = null,
    @SerialName("public_contact_phone") val publicContactPhone: String? = null,
    @SerialName("consent_version") val consentVersion: String? = null,
    @SerialName("published_at") val publishedAt: String? = null,
    @SerialName("checklist") val checklist: List<HubChecklistItem> = emptyList(),
    @SerialName("publishable") val publishable: Boolean = false,
    @SerialName("runs_classes") val runsClasses: Boolean = false,
    @SerialName("consent_version_current") val consentVersionCurrent: String,
    @SerialName("is_centre") val isCentre: Boolean = false,
)

/**
 * The body of `PUT /v1/hub/listing`: an omitted field is left alone and
 * an empty string clears a text field.
 *
 * @property slug The public path segment
 * @property publicName The name shown publicly
 * @property headlineEn The English headline
 * @property headlineBn The Bangla headline
 * @property bioEn The English biography
 * @property bioBn The Bangla biography
 * @property qualifications Qualifications
 * @property teachingMode How the owner teaches
 * @property districtCode The district's BBS code
 * @property upazilaCode The upazila's BBS code
 * @property streetAddress A centre's street address
 * @property publicContactPhone The one number shown publicly
 */
@Serializable
data class OwnerListingUpdateRequest(
    @SerialName("slug") val slug: String? = null,
    @SerialName("public_name") val publicName: String? = null,
    @SerialName("headline_en") val headlineEn: String? = null,
    @SerialName("headline_bn") val headlineBn: String? = null,
    @SerialName("bio_en") val bioEn: String? = null,
    @SerialName("bio_bn") val bioBn: String? = null,
    @SerialName("qualifications") val qualifications: String? = null,
    @SerialName("teaching_mode") val teachingMode: List<String>? = null,
    @SerialName("district_code") val districtCode: String? = null,
    @SerialName("upazila_code") val upazilaCode: String? = null,
    @SerialName("street_address") val streetAddress: String? = null,
    @SerialName("public_contact_phone") val publicContactPhone: String? = null,
)

/**
 * The body of `POST /v1/hub/listing/publish`.
 *
 * @property consentVersion The version of the terms the server named last
 */
@Serializable
data class PublishRequest(
    @SerialName("consent_version") val consentVersion: String,
)

/**
 * Whether the caller may claim a slug.
 *
 * @property slug The slug asked about
 * @property available True when it is well formed and nobody else holds it
 */
@Serializable
data class SlugAvailability(
    @SerialName("slug") val slug: String,
    @SerialName("available") val available: Boolean,
)

/**
 * One division, district or upazila.
 *
 * @property code The BBS geocode
 * @property kind `division`, `district` or `upazila`
 * @property nameEn The English name
 * @property nameBn The Bangla name
 */
@Serializable
data class AreaOption(
    @SerialName("code") val code: String,
    @SerialName("kind") val kind: String,
    @SerialName("name_en") val nameEn: String,
    @SerialName("name_bn") val nameBn: String,
)

/**
 * One of the owner's batches with its listing, if it has one yet.
 *
 * @property batchId The batch
 * @property batchName Its name
 * @property subjects Its subject names
 * @property status `draft` before any listing row exists
 * @property slug The public path segment
 * @property descriptionEn The English description
 * @property descriptionBn The Bangla description
 * @property syllabusEn The English syllabus
 * @property syllabusBn The Bangla syllabus
 * @property classLevels The class levels taught
 * @property curriculum The curriculum
 * @property subjectTags Public subject tags
 * @property mode How the batch is taught
 * @property admissions `open`, `waitlist` or `closed`
 * @property showFee Whether the fee is public, or null before a listing
 * @property showSchedule Whether the timetable is public, or null
 * @property fee The batch fee, only while the owner chose to show it; a
 *   JSON string on the wire, never a number [TC-7]
 * @property teacherNames The teachers the page may name
 * @property checklist Each requirement and whether it is met
 * @property publishable Whether every requirement is met, decided by the server
 */
@Serializable
data class BatchListingResponse(
    @SerialName("batch_id") val batchId: String,
    @SerialName("batch_name") val batchName: String,
    @SerialName("subjects") val subjects: List<String> = emptyList(),
    @SerialName("status") val status: String,
    @SerialName("slug") val slug: String? = null,
    @SerialName("description_en") val descriptionEn: String? = null,
    @SerialName("description_bn") val descriptionBn: String? = null,
    @SerialName("syllabus_en") val syllabusEn: String? = null,
    @SerialName("syllabus_bn") val syllabusBn: String? = null,
    @SerialName("class_levels") val classLevels: List<String> = emptyList(),
    @SerialName("curriculum") val curriculum: String? = null,
    @SerialName("subject_tags") val subjectTags: List<String> = emptyList(),
    @SerialName("mode") val mode: String? = null,
    @SerialName("admissions") val admissions: String? = null,
    @SerialName("show_fee") val showFee: Boolean? = null,
    @SerialName("show_schedule") val showSchedule: Boolean? = null,
    @SerialName("fee") val fee: Money? = null,
    @SerialName("teacher_names") val teacherNames: List<String> = emptyList(),
    @SerialName("checklist") val checklist: List<HubChecklistItem> = emptyList(),
    @SerialName("publishable") val publishable: Boolean = false,
)

/**
 * The body of `PUT /v1/batches/{id}/listing`.
 *
 * @property slug The public path segment
 * @property descriptionEn The English description
 * @property descriptionBn The Bangla description
 * @property syllabusEn The English syllabus
 * @property syllabusBn The Bangla syllabus
 * @property classLevels The class levels taught
 * @property curriculum The curriculum; empty clears it
 * @property subjectTags Public subject tags
 * @property mode How the batch is taught; empty clears it
 * @property admissions `open`, `waitlist` or `closed`
 * @property showFee Whether the fee is public
 * @property showSchedule Whether the weekly timetable is public
 */
@Serializable
data class BatchListingUpdateRequest(
    @SerialName("slug") val slug: String? = null,
    @SerialName("description_en") val descriptionEn: String? = null,
    @SerialName("description_bn") val descriptionBn: String? = null,
    @SerialName("syllabus_en") val syllabusEn: String? = null,
    @SerialName("syllabus_bn") val syllabusBn: String? = null,
    @SerialName("class_levels") val classLevels: List<String>? = null,
    @SerialName("curriculum") val curriculum: String? = null,
    @SerialName("subject_tags") val subjectTags: List<String>? = null,
    @SerialName("mode") val mode: String? = null,
    @SerialName("admissions") val admissions: String? = null,
    @SerialName("show_fee") val showFee: Boolean? = null,
    @SerialName("show_schedule") val showSchedule: Boolean? = null,
)

/**
 * The body of `PUT /v1/centres/{id}/members/me/public-name-consent`.
 *
 * @property consent True to be named on the centre's public page
 */
@Serializable
data class ConsentRequest(
    @SerialName("consent") val consent: Boolean,
)

/**
 * One accepted centre membership of the caller, with its name consent.
 *
 * @property memberId The membership
 * @property centreId The centre, for the consent route's path
 * @property centreName The centre's name
 * @property role `manager` or `teacher`
 * @property publicNameConsent Whether the member agreed to be named publicly
 */
@Serializable
data class CentreMembership(
    @SerialName("member_id") val memberId: String,
    @SerialName("centre_id") val centreId: String,
    @SerialName("centre_name") val centreName: String,
    @SerialName("role") val role: String,
    @SerialName("public_name_consent") val publicNameConsent: Boolean,
)

/** A listing's status, as the server names it. */
enum class ListingStatus(val wire: String) {
    /** Not public yet. */
    DRAFT("draft"),

    /** Public. */
    PUBLISHED("published"),

    /** Taken down by the owner; the text is kept. */
    HIDDEN("hidden"),

    /** Taken down by an administrator; read-only until they lift it. */
    SUSPENDED("suspended"),

    /** A status this version does not know; never edited from here. */
    UNKNOWN(""),
    ;

    companion object {
        /**
         * Read the server's value.
         *
         * @param wire The server's `status`
         * @return The status; anything unrecognised reads as [UNKNOWN], which is read-only
         */
        fun fromWire(wire: String): ListingStatus =
            entries.firstOrNull { it.wire == wire && it != UNKNOWN } ?: UNKNOWN
    }
}

/** How an owner or a batch is taught, as the server names it. */
enum class TeachingMode(val wire: String) {
    /** At a place. */
    IN_PERSON("in_person"),

    /** At the student's home. */
    HOME_VISIT("home_visit"),

    /** Over the internet. */
    ONLINE("online"),
}

/** Whether a batch is taking students, as the server names it. */
enum class Admissions(val wire: String) {
    /** Taking students. */
    OPEN("open"),

    /** Full, with a waiting list. */
    WAITLIST("waitlist"),

    /** Not taking students. */
    CLOSED("closed"),
}

/** The exact fallback label the server sends for a member who has not agreed to be named. */
const val CENTRE_FACULTY: String = "Centre faculty"

/**
 * Teacher names for display. The server's fallback label is shown in the
 * reader's language; every other name is shown as the server sent it.
 *
 * @param names The server's `teacher_names`
 * @param centreFaculty The fallback label in the reader's language
 * @return The names, comma separated
 */
fun teacherLine(names: List<String>, centreFaculty: String): String =
    names.joinToString(", ") { if (it == CENTRE_FACULTY) centreFaculty else it }

/**
 * What the owner has typed, as strings so an input never holds null.
 *
 * @property publicName The name shown publicly
 * @property slug The public path segment
 * @property headlineEn The English headline
 * @property headlineBn The Bangla headline
 * @property bioEn The English biography
 * @property bioBn The Bangla biography
 * @property qualifications Qualifications
 * @property modes The chosen teaching modes, as wire values
 * @property districtCode The district's BBS code
 * @property upazilaCode The upazila's BBS code
 * @property streetAddress A centre's street address
 * @property phone The one number shown publicly
 */
data class HubDraft(
    val publicName: String = "",
    val slug: String = "",
    val headlineEn: String = "",
    val headlineBn: String = "",
    val bioEn: String = "",
    val bioBn: String = "",
    val qualifications: String = "",
    val modes: List<String> = emptyList(),
    val districtCode: String = "",
    val upazilaCode: String = "",
    val streetAddress: String = "",
    val phone: String = "",
)

/**
 * The draft a listing starts the editor from.
 *
 * @param l The server's listing
 * @return Its fields as typed text
 */
fun draftOf(l: OwnerListingResponse): HubDraft =
    HubDraft(
        publicName = l.publicName,
        slug = l.slug.orEmpty(),
        headlineEn = l.headlineEn.orEmpty(),
        headlineBn = l.headlineBn.orEmpty(),
        bioEn = l.bioEn.orEmpty(),
        bioBn = l.bioBn.orEmpty(),
        qualifications = l.qualifications.orEmpty(),
        modes = l.teachingMode,
        districtCode = l.districtCode.orEmpty(),
        upazilaCode = l.upazilaCode.orEmpty(),
        streetAddress = l.streetAddress.orEmpty(),
        phone = l.publicContactPhone.orEmpty(),
    )

/**
 * The fields that changed, or null when nothing did.
 *
 * An omitted field is left alone by the server and an empty string clears
 * a text field, so only what the person touched is sent. The district and
 * upazila travel together: the server checks the upazila lies in the
 * district. This is a diff of typed text, not a rule about the listing.
 *
 * @param draft What the person typed
 * @param saved What the server holds
 * @return The request, or null for no change
 */
fun updateBody(draft: HubDraft, saved: OwnerListingResponse): OwnerListingUpdateRequest? {
    val was = draftOf(saved)
    val areaChanged = draft.districtCode != was.districtCode || draft.upazilaCode != was.upazilaCode
    val body =
        OwnerListingUpdateRequest(
            publicName = draft.publicName.trim().takeIf { it != was.publicName },
            slug = draft.slug.trim().takeIf { it != was.slug },
            headlineEn = draft.headlineEn.takeIf { it != was.headlineEn },
            headlineBn = draft.headlineBn.takeIf { it != was.headlineBn },
            bioEn = draft.bioEn.takeIf { it != was.bioEn },
            bioBn = draft.bioBn.takeIf { it != was.bioBn },
            qualifications = draft.qualifications.takeIf { it != was.qualifications },
            teachingMode = draft.modes.takeIf { it.toSet() != was.modes.toSet() },
            districtCode = draft.districtCode.takeIf { areaChanged },
            upazilaCode = draft.upazilaCode.takeIf { areaChanged },
            streetAddress = draft.streetAddress.takeIf { it != was.streetAddress },
            publicContactPhone = draft.phone.trim().takeIf { it != was.phone },
        )
    return body.takeIf { it != OwnerListingUpdateRequest() }
}

/**
 * The division a district sits in. A BBS district code is its division's
 * code followed by two digits (`BD2019` in `BD20`); an unrecognised code
 * gives an empty string and the person picks the division again.
 *
 * @param districtCode The saved district
 * @param divisionCodes The server's division codes
 * @return The division's code, or an empty string
 */
fun divisionOf(districtCode: String, divisionCodes: List<String>): String =
    divisionCodes.firstOrNull { districtCode.startsWith(it) && districtCode != it }.orEmpty()

/**
 * What the batch editor has typed.
 *
 * @property slug The public path segment
 * @property descriptionEn The English description
 * @property descriptionBn The Bangla description
 * @property syllabusEn The English syllabus
 * @property syllabusBn The Bangla syllabus
 * @property levels Class levels, comma separated
 * @property curriculum The curriculum
 * @property tags Subject tags, comma separated
 * @property mode The teaching mode's wire value, or empty for none
 * @property admissions The admissions state's wire value
 * @property showFee Whether the fee is public
 * @property showSchedule Whether the timetable is public
 */
data class BatchDraft(
    val slug: String = "",
    val descriptionEn: String = "",
    val descriptionBn: String = "",
    val syllabusEn: String = "",
    val syllabusBn: String = "",
    val levels: String = "",
    val curriculum: String = "",
    val tags: String = "",
    val mode: String = "",
    val admissions: String = Admissions.OPEN.wire,
    val showFee: Boolean = false,
    val showSchedule: Boolean = false,
)

/**
 * The draft a batch listing starts the editor from.
 *
 * @param b The server's batch listing
 * @return Its fields as typed text
 */
fun batchDraftOf(b: BatchListingResponse): BatchDraft =
    BatchDraft(
        slug = b.slug.orEmpty(),
        descriptionEn = b.descriptionEn.orEmpty(),
        descriptionBn = b.descriptionBn.orEmpty(),
        syllabusEn = b.syllabusEn.orEmpty(),
        syllabusBn = b.syllabusBn.orEmpty(),
        levels = b.classLevels.joinToString(", "),
        curriculum = b.curriculum.orEmpty(),
        tags = b.subjectTags.joinToString(", "),
        mode = b.mode.orEmpty(),
        admissions = b.admissions ?: Admissions.OPEN.wire,
        showFee = b.showFee ?: false,
        showSchedule = b.showSchedule ?: false,
    )

/**
 * A comma-separated field as a list, without blanks.
 *
 * @param text What was typed, split on `,` or the Bangla `،`
 * @return The trimmed, non-empty parts
 */
fun splitList(text: String): List<String> = text.split(',', '،').map { it.trim() }.filter { it.isNotEmpty() }

/**
 * A batch listing's save. The first save must say whether the fee and the
 * timetable are public, so both flags always travel; the rest is the full
 * draft, which the server treats as the new values.
 *
 * @param d What was typed
 * @return The request
 */
fun batchBody(d: BatchDraft): BatchListingUpdateRequest =
    BatchListingUpdateRequest(
        slug = d.slug.trim().ifEmpty { null },
        descriptionEn = d.descriptionEn,
        descriptionBn = d.descriptionBn,
        syllabusEn = d.syllabusEn,
        syllabusBn = d.syllabusBn,
        classLevels = splitList(d.levels),
        curriculum = d.curriculum.trim(),
        subjectTags = splitList(d.tags),
        mode = d.mode,
        admissions = d.admissions,
        showFee = d.showFee,
        showSchedule = d.showSchedule,
    )
