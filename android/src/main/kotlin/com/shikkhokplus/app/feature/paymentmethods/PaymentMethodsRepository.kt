package com.shikkhokplus.app.feature.paymentmethods

import com.shikkhokplus.app.core.network.PaymentMethodDto
import com.shikkhokplus.app.feature.auth.AuthResult

/**
 * Which kind of destination a method is.
 *
 * @property wire The value the server uses
 */
enum class MethodKind(val wire: String) {
    /** A mobile banking number. */
    MOBILE("mobile"),

    /** A bank account. */
    BANK("bank"),
    ;

    companion object {
        /**
         * Read the server's value.
         *
         * @param wire The server's `kind`
         * @return The kind; anything unrecognised reads as mobile
         */
        fun fromWire(wire: String): MethodKind = entries.firstOrNull { it.wire == wire } ?: MOBILE
    }
}

/**
 * What the teacher typed for one method; the server validates it.
 *
 * @property kind Mobile or bank
 * @property provider The mobile service, or the bank's name
 * @property mobileNumber The number, mobile only
 * @property accountNumber The account number, bank only
 * @property accountName The account holder, bank only
 * @property branchName The branch, bank only
 * @property note Optional text shown with the method
 */
data class PaymentMethodDraft(
    val kind: MethodKind,
    val provider: String? = null,
    val mobileNumber: String? = null,
    val accountNumber: String? = null,
    val accountName: String? = null,
    val branchName: String? = null,
    val note: String? = null,
)

/** What the payment-methods screens need from the network. */
interface PaymentMethodsRepository {
    /**
     * Read the teacher's live methods.
     *
     * @return The methods in display order, or why not
     */
    suspend fun list(): AuthResult<List<PaymentMethodDto>>

    /**
     * Add a method.
     *
     * @param draft What was typed
     * @return The stored method, or why the server refused
     */
    suspend fun create(draft: PaymentMethodDraft): AuthResult<PaymentMethodDto>

    /**
     * Replace a method in full.
     *
     * @param methodId The method
     * @param draft What was typed
     * @return The stored method, or why the server refused
     */
    suspend fun update(methodId: String, draft: PaymentMethodDraft): AuthResult<PaymentMethodDto>

    /**
     * Retire a method; past payments keep it.
     *
     * @param methodId The method
     * @return Nothing on success, or why the server refused
     */
    suspend fun retire(methodId: String): AuthResult<Unit>
}
