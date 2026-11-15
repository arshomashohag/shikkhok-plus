package com.shikkhokplus.app.feature.hublisting

import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.TokenStore
import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.ContentType
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull

/** The hub's network calls over a mock transport: paths, verbs, bodies. */
class HttpHubApiTest {

    private val json = headersOf("Content-Type", ContentType.Application.Json.toString())

    private val listingJson =
        """{"status":"draft","slug":null,"public_name":"Rahima","teaching_mode":[],
        "checklist":[],"publishable":false,"runs_classes":false,
        "consent_version_current":"2026-11-14","is_centre":false}"""

    private val batchJson =
        """{"batch_id":"b-1","batch_name":"Physics","status":"draft","fee":"900.00",
        "teacher_names":[],"checklist":[],"publishable":false}"""

    private fun api(engine: MockEngine) =
        HttpHubApi(ApiClient.build("https://staging.example", engine, TokenStore.InMemory()))

    private fun body(engine: MockEngine) = (engine.requestHistory.single().body as TextContent).text

    @Test
    fun `the listing is read, saved, published and unpublished at the server's paths`() = runTest {
        val engine = MockEngine { respond(listingJson, HttpStatusCode.OK, json) }
        val api = api(engine)

        assertIs<AuthResult.Ok<OwnerListingResponse>>(api.listing())
        api.save(OwnerListingUpdateRequest(headlineEn = "Hi"))
        api.publish("2026-11-14")
        api.unpublish()

        val seen = engine.requestHistory.map { it.method to it.url.encodedPath }
        assertEquals(
            listOf(
                HttpMethod.Get to "/v1/hub/listing",
                HttpMethod.Put to "/v1/hub/listing",
                HttpMethod.Post to "/v1/hub/listing/publish",
                HttpMethod.Post to "/v1/hub/listing/unpublish",
            ),
            seen,
        )
        assertEquals("""{"headline_en":"Hi"}""", (engine.requestHistory[1].body as TextContent).text)
        assertEquals("""{"consent_version":"2026-11-14"}""", (engine.requestHistory[2].body as TextContent).text)
    }

    @Test
    fun `a slug is checked as an encoded path segment`() = runTest {
        val engine = MockEngine { respond("""{"slug":"a b","available":false}""", HttpStatusCode.OK, json) }

        val result = assertIs<AuthResult.Ok<SlugAvailability>>(api(engine).slugAvailable("a b"))

        assertEquals("/v1/hub/slugs/a%20b", engine.requestHistory.single().url.encodedPath)
        assertEquals(false, result.value.available)
    }

    @Test
    fun `areas ask for the divisions with no parent and a district's areas with one`() = runTest {
        val engine = MockEngine { respond("[]", HttpStatusCode.OK, json) }
        val api = api(engine)

        api.areas(null)
        api.areas("BD20")

        assertNull(engine.requestHistory[0].url.parameters["parent"])
        assertEquals("BD20", engine.requestHistory[1].url.parameters["parent"])
        assertEquals("/v1/hub/areas", engine.requestHistory[1].url.encodedPath)
    }

    @Test
    fun `batch listings are listed, saved, published and unpublished by batch`() = runTest {
        val engine = MockEngine { respond(batchJson, HttpStatusCode.OK, json) }
        val api = api(engine)

        api.saveBatch("b-1", BatchListingUpdateRequest(showFee = true))
        api.publishBatch("b-1")
        api.unpublishBatch("b-1")

        assertEquals(
            listOf(
                HttpMethod.Put to "/v1/batches/b-1/listing",
                HttpMethod.Post to "/v1/batches/b-1/listing/publish",
                HttpMethod.Post to "/v1/batches/b-1/listing/unpublish",
            ),
            engine.requestHistory.map { it.method to it.url.encodedPath },
        )
    }

    @Test
    fun `the list of batch listings decodes the fee through Money`() = runTest {
        val engine = MockEngine { respond("[$batchJson]", HttpStatusCode.OK, json) }

        val ok = assertIs<AuthResult.Ok<List<BatchListingResponse>>>(api(engine).batchListings())

        assertEquals("900.00", ok.value.single().fee.toString())
        assertEquals("/v1/hub/batch-listings", engine.requestHistory.single().url.encodedPath)
    }

    @Test
    fun `name consent reads the memberships and sends the bare flag to the centre`() = runTest {
        val engine =
            MockEngine { request ->
                if (request.method == HttpMethod.Put) {
                    respond("", HttpStatusCode.NoContent)
                } else {
                    respond(
                        """[{"member_id":"m-1","centre_id":"c-1","centre_name":"Udayan","role":"teacher",
                        "public_name_consent":true}]""",
                        HttpStatusCode.OK,
                        json,
                    )
                }
            }
        val api = api(engine)

        val memberships = assertIs<AuthResult.Ok<List<CentreMembership>>>(api.centreMemberships())
        assertEquals(true, memberships.value.single().publicNameConsent)
        assertIs<AuthResult.Ok<Unit>>(api.setNameConsent("c-1", false))

        val put = engine.requestHistory.last()
        assertEquals("/v1/centres/c-1/members/me/public-name-consent", put.url.encodedPath)
        assertEquals("""{"consent":false}""", (put.body as TextContent).text)
    }

    @Test
    fun `a refusal carries the servers message key`() = runTest {
        val engine =
            MockEngine {
                respond(
                    """{"error":{"code":"HUB_LISTING_SUSPENDED","retryable":false,
                    "message_key":"hub.listing_suspended"}}""",
                    HttpStatusCode.Conflict,
                    json,
                )
            }

        val refused = assertIs<AuthResult.Refused>(api(engine).save(OwnerListingUpdateRequest(slug = "x")))

        assertEquals("hub.listing_suspended", refused.envelope.error.messageKey)
    }
}
