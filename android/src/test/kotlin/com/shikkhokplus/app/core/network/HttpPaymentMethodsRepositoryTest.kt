package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.paymentmethods.MethodKind
import com.shikkhokplus.app.feature.paymentmethods.PaymentMethodDraft
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

/** The payment-methods repository over a mock transport, and its DTO. */
class HttpPaymentMethodsRepositoryTest {

    private val json = headersOf("Content-Type", ContentType.Application.Json.toString())

    private val mobileJson =
        """{"method_id":"m1","kind":"mobile","provider":"bKash",
        "mobile_number":"01712345678","account_number":null,"account_name":null,
        "branch_name":null,"note":"Send Money"}"""

    private fun repo(engine: MockEngine) =
        HttpPaymentMethodsRepository(
            ApiClient.build("https://staging.example", engine, TokenStore.InMemory()),
        )

    @Test
    fun `a method decodes from the servers shape`() = runTest {
        val engine = MockEngine { respond("[$mobileJson]", HttpStatusCode.OK, json) }

        val ok = assertIs<AuthResult.Ok<List<PaymentMethodDto>>>(repo(engine).list())

        val method = ok.value.single()
        assertEquals("m1", method.methodId)
        assertEquals("mobile", method.kind)
        assertEquals("01712345678", method.mobileNumber)
        assertEquals(null, method.accountName)
        assertEquals("/v1/payment-methods", engine.requestHistory.single().url.encodedPath)
    }

    @Test
    fun `create posts the draft with its kind`() = runTest {
        val engine = MockEngine { respond(mobileJson, HttpStatusCode.Created, json) }

        val result =
            repo(engine).create(
                PaymentMethodDraft(
                    kind = MethodKind.MOBILE,
                    provider = "bKash",
                    mobileNumber = "01712345678",
                ),
            )

        assertIs<AuthResult.Ok<PaymentMethodDto>>(result)
        val sent = engine.requestHistory.single()
        assertEquals(HttpMethod.Post, sent.method)
        assertEquals("/v1/payment-methods", sent.url.encodedPath)
        val body = (sent.body as TextContent).text
        assertEquals(true, body.contains("\"kind\":\"mobile\""))
        assertEquals(true, body.contains("\"mobile_number\":\"01712345678\""))
    }

    @Test
    fun `update patches the method by id`() = runTest {
        val engine = MockEngine { respond(mobileJson, HttpStatusCode.OK, json) }

        repo(engine).update(
            "m1",
            PaymentMethodDraft(kind = MethodKind.MOBILE, provider = "Nagad", mobileNumber = "018"),
        )

        val sent = engine.requestHistory.single()
        assertEquals(HttpMethod.Patch, sent.method)
        assertEquals("/v1/payment-methods/m1", sent.url.encodedPath)
    }

    @Test
    fun `retire deletes the method`() = runTest {
        val engine = MockEngine { respond("", HttpStatusCode.NoContent) }

        val result = repo(engine).retire("m1")

        assertEquals(AuthResult.Ok(Unit), result)
        val sent = engine.requestHistory.single()
        assertEquals(HttpMethod.Delete, sent.method)
        assertEquals("/v1/payment-methods/m1", sent.url.encodedPath)
    }

    @Test
    fun `a validation refusal keeps the servers message key`() = runTest {
        val engine =
            MockEngine {
                respond(
                    """{"error":{"code":"METHOD_FIELDS_INCOMPLETE",
                    "message_key":"fees.method.fields_incomplete","retryable":false}}""",
                    HttpStatusCode.BadRequest,
                    json,
                )
            }

        val refused =
            assertIs<AuthResult.Refused>(
                repo(engine).create(PaymentMethodDraft(kind = MethodKind.BANK)),
            )

        assertEquals("fees.method.fields_incomplete", refused.envelope.error.messageKey)
    }
}
