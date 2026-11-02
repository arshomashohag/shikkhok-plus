package com.shikkhokplus.app.feature.paymentmethods

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.PaymentMethodDto
import com.shikkhokplus.app.feature.auth.AuthResult

/** A scripted [PaymentMethodsRepository] that records what it was asked. */
class FakePaymentMethodsRepository : PaymentMethodsRepository {
    var listResults: MutableList<AuthResult<List<PaymentMethodDto>>> =
        mutableListOf(AuthResult.Ok(emptyList()))
    var writeResult: AuthResult<PaymentMethodDto> = AuthResult.Ok(mobileMethod())
    var retireResult: AuthResult<Unit> = AuthResult.Ok(Unit)
    var lists = 0
    var created: MutableList<PaymentMethodDraft> = mutableListOf()
    var updated: MutableList<Pair<String, PaymentMethodDraft>> = mutableListOf()
    var retired: MutableList<String> = mutableListOf()

    override suspend fun list(): AuthResult<List<PaymentMethodDto>> {
        lists++
        return if (listResults.size > 1) listResults.removeAt(0) else listResults.first()
    }

    override suspend fun create(draft: PaymentMethodDraft): AuthResult<PaymentMethodDto> {
        created += draft
        return writeResult
    }

    override suspend fun update(
        methodId: String,
        draft: PaymentMethodDraft,
    ): AuthResult<PaymentMethodDto> {
        updated += methodId to draft
        return writeResult
    }

    override suspend fun retire(methodId: String): AuthResult<Unit> {
        retired += methodId
        return retireResult
    }

    companion object {
        fun mobileMethod(id: String = "m1") =
            PaymentMethodDto(
                methodId = id,
                kind = "mobile",
                provider = "bKash",
                mobileNumber = "01712345678",
                accountNumber = null,
                accountName = null,
                branchName = null,
                note = "Use Send Money, not Cash Out",
            )

        fun bankMethod(id: String = "b1") =
            PaymentMethodDto(
                methodId = id,
                kind = "bank",
                provider = "Dutch-Bangla Bank",
                mobileNumber = null,
                accountNumber = "1234564521",
                accountName = "Rahima Akter",
                branchName = "Mirpur branch",
                note = null,
            )

        fun refusal(key: String, retryable: Boolean = false) =
            AuthResult.Refused(ErrorEnvelope(ErrorBody("X", retryable, key)))
    }
}
