package com.shikkhokplus.app.feature.auth.ui

import com.shikkhokplus.app.core.model.Identifier

/**
 * Everything the sign-in screen can ask for.
 *
 * Bundled for the reason [com.shikkhokplus.app.feature.mfa.ui.TwoStepActions]
 * is: one screen with three ways in has more callbacks than a readable
 * argument list, and every one has a harmless default so a test supplies
 * only the ones it drives.
 *
 * @property onSignIn Sign in with an identifier and a password
 * @property onStartCodeFlow Open the code flow ("Forgot password?",
 *   "First time with a password? Get a code")
 * @property onBackToSignIn Leave the code flow for the password sign-in
 * @property onRequestCode Send a code to an identifier
 * @property onSubmitCode Check the six digits
 * @property onResendCode Ask for a new code to the same identifier
 * @property onChangeNumber Back from the code step to the identifier
 * @property onChoosePassword Finish the code flow: password, its second
 *   copy, and the authenticator or recovery code when one is asked for
 * @property onToggleSetupRecovery Switch the choose-password form between
 *   the authenticator code and a recovery code
 * @property onSubmitSecondStep Check the authenticator or recovery code
 *   after a password sign-in
 * @property onToggleRecoveryCode Switch that step's kind of code
 * @property onRetry Repeat a failure the server marked retryable
 * @property onGoToSignup Open sign-up
 */
data class AuthActions(
    val onSignIn: (Identifier, String) -> Unit = { _, _ -> },
    val onStartCodeFlow: () -> Unit = {},
    val onBackToSignIn: () -> Unit = {},
    val onRequestCode: (Identifier) -> Unit = {},
    val onSubmitCode: (String) -> Unit = {},
    val onResendCode: () -> Unit = {},
    val onChangeNumber: () -> Unit = {},
    val onChoosePassword: (String, String, String) -> Unit = { _, _, _ -> },
    val onToggleSetupRecovery: () -> Unit = {},
    val onSubmitSecondStep: (String) -> Unit = {},
    val onToggleRecoveryCode: () -> Unit = {},
    val onRetry: () -> Unit = {},
    val onGoToSignup: () -> Unit = {},
)
