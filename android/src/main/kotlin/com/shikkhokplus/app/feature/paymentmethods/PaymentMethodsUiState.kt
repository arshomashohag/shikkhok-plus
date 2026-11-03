package com.shikkhokplus.app.feature.paymentmethods

/**
 * One method as the list draws it.
 *
 * @property methodId The method
 * @property kind Mobile or bank
 * @property title The service or bank name
 * @property detail The number, or the holder and the account's last digits
 * @property extra A further line such as the branch, or null
 * @property note The teacher's note for payers, or null
 */
data class MethodRow(
    val methodId: String,
    val kind: MethodKind,
    val title: String,
    val detail: String,
    val extra: String?,
    val note: String?,
)

/** Everything P1 renders. */
sealed interface PaymentMethodsUiState {
    /** Waiting for the list. */
    data object Loading : PaymentMethodsUiState

    /** The teacher has no methods yet. */
    data object Empty : PaymentMethodsUiState

    /**
     * The methods.
     *
     * @property rows One per method
     * @property removeFailedKey Message key when the last removal failed
     */
    data class Loaded(
        val rows: List<MethodRow>,
        val removeFailedKey: String? = null,
    ) : PaymentMethodsUiState

    /**
     * The read failed.
     *
     * @property messageKey The server's key, or the offline key
     * @property retryable Whether to offer a retry
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : PaymentMethodsUiState
}
