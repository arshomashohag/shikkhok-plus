package com.shikkhokplus.app.feature.hublisting

import com.shikkhokplus.app.core.network.ApiClient
import kotlinx.serialization.SerializationException
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The hub models' half of the money boundary and of the wire contract.
 *
 * A batch listing's fee is the one money value on this surface. The
 * server sends it as a JSON string, only while the owner chose to show
 * it, and the client must decode it through `Money` and refuse a JSON
 * number loudly [TC-7, D-20].
 */
class HubModelsSerializationTest {

    private fun batch(fee: String) =
        """
        {"batch_id":"b-1","batch_name":"Physics 9","subjects":["Physics"],"status":"draft",
         "slug":null,"description_en":null,"description_bn":null,"syllabus_en":null,
         "syllabus_bn":null,"class_levels":[],"curriculum":null,"subject_tags":[],
         "mode":null,"admissions":null,"show_fee":null,"show_schedule":null,
         "fee":$fee,"teacher_names":["Centre faculty"],"checklist":[],"publishable":false}
        """.trimIndent()

    @Test
    fun `fee decodes from string and fails loudly on json number`() {
        val decoded = ApiClient.json.decodeFromString<BatchListingResponse>(batch("\"1500.00\""))
        assertEquals("1500.00", decoded.fee.toString())

        val failure =
            assertFailsWith<SerializationException> {
                ApiClient.json.decodeFromString<BatchListingResponse>(batch("1500.00"))
            }
        assertTrue(failure.message!!.contains("JSON string"), "got: ${failure.message}")
    }

    @Test
    fun `a hidden fee decodes as null`() {
        assertNull(ApiClient.json.decodeFromString<BatchListingResponse>(batch("null")).fee)
    }

    @Test
    fun `the owner listing decodes the server's decisions and ignores unknown fields`() {
        val decoded =
            ApiClient.json.decodeFromString<OwnerListingResponse>(
                """
                {"status":"draft","slug":null,"public_name":"রহিমা","public_name_latin":"Rahima",
                 "headline_en":null,
                 "headline_bn":null,"bio_en":null,"bio_bn":null,"qualifications":null,
                 "teaching_mode":["online"],"district_code":null,"upazila_code":null,
                 "street_address":null,"public_contact_phone":null,"consent_version":null,
                 "published_at":null,"checklist":[{"key":"slug","done":false}],
                 "publishable":false,"runs_classes":true,"consent_version_current":"2026-11-14",
                 "is_centre":true,"added_later":1}
                """.trimIndent(),
            )

        assertEquals("Rahima", decoded.publicNameLatin)
        assertEquals(listOf(HubChecklistItem("slug", false)), decoded.checklist)
        assertTrue(decoded.runsClasses && decoded.isCentre)
        assertEquals("2026-11-14", decoded.consentVersionCurrent)
    }

    @Test
    fun `an update sends only what changed and a consent sends the bare flag`() {
        val body =
            ApiClient.json.encodeToString(
                OwnerListingUpdateRequest.serializer(),
                OwnerListingUpdateRequest(headlineEn = ""),
            )
        assertEquals("""{"headline_en":""}""", body)
        assertEquals(
            """{"public_name_latin":"Rahima"}""",
            ApiClient.json.encodeToString(
                OwnerListingUpdateRequest.serializer(),
                OwnerListingUpdateRequest(publicNameLatin = "Rahima"),
            ),
        )
        assertEquals(
            """{"consent":true}""",
            ApiClient.json.encodeToString(ConsentRequest.serializer(), ConsentRequest(true)),
        )
    }
}
