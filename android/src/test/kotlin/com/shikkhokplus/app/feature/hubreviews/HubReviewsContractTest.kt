package com.shikkhokplus.app.feature.hubreviews

import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.OpenApi
import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerializationException
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * The review models against what the server documents in `openapi.json`.
 *
 * The review API is read here, not in the repository-wide conformance
 * gate, because that gate scans `Http*Repository` files and this API is
 * not one. So the same three checks are made for it: every documented
 * shape decodes, no field is read that the server never sends, and
 * every body sent is one the server's schema accepts.
 */
class HubReviewsContractTest {

    private class Read(val method: String, val path: String, val serializer: KSerializer<*>)

    private val reads =
        listOf(
            Read("get", "/v1/hub/reviewable", ListSerializer(ReviewableBatch.serializer())),
            Read("get", MY_REVIEW, MyReviewResponse.serializer()),
            Read("put", MY_REVIEW, MyReviewResponse.serializer()),
            Read("get", "/v1/hub/reviews", OwnerReviewsResponse.serializer()),
            Read("put", REPLY, OwnerReview.serializer()),
        )

    private fun bodyOf(read: Read): JsonObject =
        OpenApi.operation(read.method, read.path)?.let { OpenApi.success(it).second }
            ?: error("no 200 body documented for ${read.method} ${read.path}")

    @Test
    fun `every review read decodes every shape the server documents`() {
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
    fun `no review read expects a field the server never sends`() {
        val failures =
            reads.flatMap { OpenApi.unknownFields(it.serializer.descriptor, bodyOf(it), it.path) }

        assertEquals(emptyList(), failures, failures.joinToString("\n"))
    }

    @Test
    fun `every review write is one the server accepts`() {
        val writes =
            listOf(
                Triple(MY_REVIEW, ReviewWrite.serializer(), ReviewWrite(rating = 4, body = "Clear")),
                Triple(MY_REVIEW, ReviewWrite.serializer(), ReviewWrite(rating = 1)),
                Triple(REPLY, ReplyWrite.serializer(), ReplyWrite("Thank you")),
            )
        val failures =
            writes.flatMap { (path, serializer, value) ->
                @Suppress("UNCHECKED_CAST")
                val body = ApiClient.json.encodeToJsonElement(serializer as KSerializer<Any>, value)
                val schema = OpenApi.requestSchema(OpenApi.operation("put", path)!!)!!
                OpenApi.violations(body, schema, path)
            }

        assertEquals(emptyList(), failures, failures.joinToString("\n"))
    }

    @Test
    fun `the rating is a whole number and the average is never read as one`() {
        // No Float or Double anywhere: a rating with a fraction is refused
        // loudly, and the average arrives as the server's label [F13, T6-a].
        assertFailsWith<SerializationException> {
            ApiClient.json.decodeFromString(
                OwnerReview.serializer(),
                """{"id":"r","batch_id":"b","rating":4.5,"tenure":"lt_6m","published_month":"2026-11"}""",
            )
        }
        val names = (0 until OwnerBatchRating.serializer().descriptor.elementsCount)
            .map { OwnerBatchRating.serializer().descriptor.getElementName(it) }
        assertTrue("average_tenths" !in names, "the client never reads average_tenths")
        assertTrue("average_label" in names)
    }

    @Test
    fun `the vocabularies are the server's`() {
        fun enumOf(schema: String, field: String): Set<String> =
            OpenApi.arms(
                OpenApi.spec["components"]!!.jsonObject["schemas"]!!.jsonObject[schema]!!
                    .jsonObject["properties"]!!.jsonObject[field]!!.jsonObject,
            ).flatMap { arm -> arm["enum"]?.jsonArray?.map { it.jsonPrimitive.content }.orEmpty() }.toSet()

        assertEquals(enumOf("ReviewableBatch", "state"), ReviewableState.entries.map { it.wire }.toSet())
        assertEquals(enumOf("MyReviewBody", "tenure"), Tenure.entries.map { it.wire }.toSet())
        // Every status a review or a reply can be in has its words.
        val statuses = enumOf("MyReviewBody", "status") + enumOf("OwnerReviewWire", "my_reply_status")
        assertTrue(statuses.isNotEmpty())
        statuses.forEach { assertTrue(statusWords(it) != null, "no words for $it") }
    }

    private companion object {
        const val MY_REVIEW = "/v1/hub/batches/{batch_id}/my-review"
        const val REPLY = "/v1/hub/reviews/{review_id}/reply"
    }
}
