package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.verify.VerifyRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
private data class ShortfallBody(
    @SerialName("approved_amount") val approvedAmount: Money,
)

@Serializable
private data class ApproveBody(
    @SerialName("approved_amount") val approvedAmount: Money,
    @SerialName("shortfall_disposition") val shortfallDisposition: String? = null,
)

/**
 * The teacher's payment checks, over HTTP (T4).
 *
 * @property client The authenticated HTTP client
 */
class HttpVerificationRepository(
    private val client: HttpClient,
) : VerifyRepository {

    override suspend fun queue(): AuthResult<VerificationQueueDto> = call { client.get("/v1/claims/queue") }

    override suspend fun preview(
        claimId: String,
        approvedAmount: Money,
    ): AuthResult<ShortfallPreviewDto> =
        call { client.post("/v1/claims/$claimId/shortfall") { setBody(ShortfallBody(approvedAmount)) } }

    override suspend fun approve(
        claimId: String,
        approvedAmount: Money,
        disposition: String?,
    ): AuthResult<Unit> =
        callDiscardingBody {
            client.post("/v1/claims/$claimId/verification") {
                setBody(ApproveBody(approvedAmount, disposition))
            }
        }

    override suspend fun reject(claimId: String): AuthResult<Unit> =
        callDiscardingBody { client.post("/v1/claims/$claimId/rejection") }
}
