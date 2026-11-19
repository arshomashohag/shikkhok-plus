package com.shikkhokplus.app.feature.hubenquiry

import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.OpenApi
import com.shikkhokplus.app.feature.hublisting.ClassLevel
import com.shikkhokplus.app.feature.hublisting.OwnerListingResponse
import com.shikkhokplus.app.feature.hublisting.OwnerListingUpdateRequest
import kotlinx.serialization.KSerializer
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The join-request models against what the server documents in
 * `openapi.json` [H5].
 *
 * Read here, not in the repository-wide conformance gate, because that gate
 * scans `Http*Repository` files and this API is not one; so the same three
 * checks are made for it: every documented shape decodes, no field is read
 * that the server never sends, and every body sent is one the server's
 * schema accepts.
 */
class HubEnquiryContractTest {

    private class Read(val method: String, val path: String, val serializer: KSerializer<*>)

    private val reads =
        listOf(
            Read("get", "$OWNER/enquiry-target", EnquiryTarget.serializer()),
            Read("post", "$OWNER/enquiries", MyEnquiry.serializer()),
            Read("get", "/v1/me/hub/enquiries", ListSerializer(MyEnquiry.serializer())),
            Read("get", "/v1/hub/enquiries", ListSerializer(OwnerEnquiry.serializer())),
            Read("get", ONE, OwnerEnquiry.serializer()),
            Read("post", "$ONE/close", OwnerEnquiry.serializer()),
            Read("get", "/v1/hub/listing", OwnerListingResponse.serializer()),
        )

    private fun bodyOf(read: Read): JsonObject =
        OpenApi.operation(read.method, read.path)?.let { OpenApi.success(it).second }
            ?: error("no success body documented for ${read.method} ${read.path}")

    @Test
    fun `every enquiry read decodes every shape the server documents`() {
        val failures =
            reads.flatMap { read ->
                OpenApi.examples(bodyOf(read)).mapNotNull { (label, body) ->
                    runCatching { ApiClient.json.decodeFromJsonElement(read.serializer, body) }
                        .exceptionOrNull()
                        ?.let { "${read.path} [$label]: ${it.message?.lineSequence()?.first()}" }
                }
            }

        assertEquals(emptyList(), failures, failures.joinToString("\n"))
    }

    @Test
    fun `no enquiry read expects a field the server never sends`() {
        val failures = reads.flatMap { OpenApi.unknownFields(it.serializer.descriptor, bodyOf(it), it.path) }

        assertEquals(emptyList(), failures, failures.joinToString("\n"))
    }

    @Test
    fun `every enquiry write is one the server accepts`() {
        val writes =
            listOf(
                Triple(
                    "post" to "$OWNER/enquiries",
                    EnquiryWrite.serializer(),
                    EnquiryWrite("Nadia", "class_8", "Wants Physics", BATCH, true, declaresAdultGuardian = true),
                ),
                Triple(
                    "post" to "$OWNER/enquiries",
                    EnquiryWrite.serializer(),
                    EnquiryWrite("Nadia", "ssc", null, null, shareContact = false, declaresAdultGuardian = true),
                ),
                Triple("post" to "$ONE/close", EnquiryClose.serializer(), EnquiryClose(EnquiryOutcome.CALL_US.wire)),
                Triple(
                    "put" to "/v1/hub/listing",
                    OwnerListingUpdateRequest.serializer(),
                    OwnerListingUpdateRequest(acceptsEnquiries = true),
                ),
            )
        val failures =
            writes.flatMap { (route, serializer, value) ->
                @Suppress("UNCHECKED_CAST")
                val body = ApiClient.json.encodeToJsonElement(serializer as KSerializer<Any>, value)
                val schema = OpenApi.requestSchema(OpenApi.operation(route.first, route.second)!!)!!
                OpenApi.violations(body, schema, route.second)
            }

        assertEquals(emptyList(), failures, failures.joinToString("\n"))
    }

    @Test
    fun `the consent and the declaration are always on the wire, never left to a default`() {
        val body =
            ApiClient.json.encodeToString(
                EnquiryWrite.serializer(),
                EnquiryWrite("Nadia", "class_8", null, null, shareContact = false, declaresAdultGuardian = true),
            )

        assertEquals(
            """{"student_name":"Nadia","class_level":"class_8","share_contact":false,"declares_adult_guardian":true}""",
            body,
        )
        // The switch sends its one field and nothing typed.
        assertEquals(
            """{"accepts_enquiries":false}""",
            ApiClient.json.encodeToString(
                OwnerListingUpdateRequest.serializer(),
                OwnerListingUpdateRequest(acceptsEnquiries = false),
            ),
        )
    }

    @Test
    fun `the vocabularies are the server's`() {
        fun enumOf(schema: String, field: String): Set<String> =
            OpenApi.arms(
                OpenApi.spec["components"]!!.jsonObject["schemas"]!!.jsonObject[schema]!!
                    .jsonObject["properties"]!!.jsonObject[field]!!.jsonObject,
            ).flatMap { arm ->
                (arm["enum"] ?: arm["items"]?.jsonObject?.get("enum"))?.jsonArray?.map { it.jsonPrimitive.content }
                    .orEmpty()
            }.toSet()

        assertEquals(enumOf("EnquiryClose", "outcome"), EnquiryOutcome.entries.map { it.wire }.toSet())
        assertEquals(enumOf("OwnerEnquiryWire", "outcomes_allowed"), EnquiryOutcome.entries.map { it.wire }.toSet())
        assertEquals(enumOf("EnquiryWrite", "class_level"), ClassLevel.entries.map { it.wire }.toSet())
        assertEquals(enumOf("MyEnquiryWire", "status"), setOf(STATUS_OPEN, "closed"))
        assertTrue(CONTACT_KIND_PHONE in enumOf("EnquiryTargetResponse", "contact_kind"))
    }

    private companion object {
        const val OWNER = "/v1/hub/owners/{owner_slug}"
        const val ONE = "/v1/hub/enquiries/{enquiry_id}"
        const val BATCH = "0b9e8d7c-6b5a-4c3d-9e2f-1a0b9c8d7e6f"
    }
}
