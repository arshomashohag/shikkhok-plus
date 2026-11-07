package com.shikkhokplus.app.core.ui

/** How many digits an authenticator code carries. */
const val AUTHENTICATOR_CODE_LENGTH: Int = 6

/** The shortest recovery code the server accepts, once trimmed. */
const val RECOVERY_CODE_MIN: Int = 10

/** The longest recovery code the server accepts, once trimmed. */
const val RECOVERY_CODE_MAX: Int = 16

/**
 * Whether a typed recovery code may be sent.
 *
 * **Format only**: the length the server's own schema checks. Whether it
 * is one of the account's codes, and unused, is the server's to say.
 *
 * @param typed The code as typed
 * @return True when the server's length check would pass
 */
fun recoveryCodeSendable(typed: String): Boolean = typed.trim().length in RECOVERY_CODE_MIN..RECOVERY_CODE_MAX

/**
 * Whether a typed authenticator code may be sent: exactly six digits.
 *
 * @param typed The code as typed
 * @return True for six ASCII digits
 */
fun authenticatorCodeSendable(typed: String): Boolean =
    typed.length == AUTHENTICATOR_CODE_LENGTH && typed.all { it in '0'..'9' }
