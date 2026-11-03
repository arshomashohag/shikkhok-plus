package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.pay.PayRepository
import com.shikkhokplus.app.feature.student.FamilyReader
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import io.ktor.client.request.setBody

/**
 * Sending money to a teacher, over HTTP.
 *
 * A student and a guardian pay through the same form over two server
 * paths, each resolving its own lens [BR7.2]; the server decides which
 * seats and methods the caller may reach.
 *
 * @property client The authenticated HTTP client
 * @property reader Whether a student or a guardian is paying
 */
class HttpPayRepository(
    private val client: HttpClient,
    private val reader: FamilyReader = FamilyReader.SELF,
) : PayRepository {

    override suspend fun seats(): AuthResult<List<StudentBatchDto>> = HttpStudentRepository(client, reader).batches()

    override suspend fun methods(enrollmentId: String): AuthResult<FamilyPaymentMethodsDto> =
        call {
            client.get(
                when (reader) {
                    FamilyReader.SELF -> "/v1/me/enrollments/$enrollmentId/payment-methods"
                    FamilyReader.GUARDIAN -> "/v1/children/$enrollmentId/payment-methods"
                },
            )
        }

    override suspend fun owed(enrollmentIds: List<String>): AuthResult<OwedTogetherDto> =
        call { client.get("/v1/payments/owed") { enrollmentIds.forEach { parameter("enrollment_id", it) } } }

    override suspend fun submit(payment: PaymentSubmitDto): AuthResult<PaymentSubmittedDto> =
        call { client.post("/v1/payments") { setBody(payment) } }
}
