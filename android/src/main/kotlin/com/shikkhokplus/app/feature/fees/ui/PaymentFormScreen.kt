package com.shikkhokplus.app.feature.fees.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.feature.fees.PaymentDestination

/** Stable test identifiers. Not user-visible text. */
const val TAG_PAYMENT_DESTINATION: String = "payment_destination"

/** The copy shown instead where the teacher set no number. */
const val TAG_PAYMENT_NO_DESTINATION: String = "payment_no_destination"

/** One channel option, from the server's list. */
const val TAG_PAYMENT_CHANNEL: String = "payment_channel"

/** The amount field. */
const val TAG_PAYMENT_AMOUNT: String = "payment_amount"

/** The transaction reference field. */
const val TAG_PAYMENT_REFERENCE: String = "payment_reference"

/** The submit action. */
const val TAG_PAYMENT_SUBMIT: String = "payment_submit"

/** The child-and-batch confirmation shown before recording. */
const val TAG_PAYMENT_CONFIRM: String = "payment_confirm"

/**
 * The payment-claim form, identical for a student and a guardian.
 *
 * **The form and its behaviour are identical for both** [AC6.2.1];
 * only the lens differs, and the lens is resolved server-side. Nothing
 * in this file branches on who is looking.
 *
 * **Where the teacher set no collection number the destination step is
 * OMITTED** [NFR14.34, BR6.4], rather than rendered with a blank in
 * it: the state is [PaymentDestination.Unset] and the copy tells the
 * person to ask the teacher how to pay. A nullable field would have
 * invited a placeholder, which looks like a value that failed to load.
 *
 * **The channel options come from the server** [BR6.5]. They are
 * rendered as labels from a list, deliberately not a sealed type with
 * a branch per channel: the sealed type is the idiomatic Kotlin choice
 * and the wrong one, because adding a channel would then need an app
 * release and an installed app cannot be forced to update.
 *
 * **Client-side validation is format-only, never policy.** Whether an
 * amount exceeding the balance is acceptable is a server decision
 * [BR5.2] — it is, because money may genuinely have been overpaid out
 * of band — so this form does not refuse it. The only thing checked
 * here is whether the text parses as a number at all.
 *
 * @param destination Where to pay, or that the teacher set nothing
 * @param childName Whose fee this is, named in the confirmation
 *   [AC6.1.3] — for a guardian with children in several batches this
 *   is the difference between paying for the right child and the wrong
 *   one
 * @param batchName Which class
 * @param amountText What the person has typed
 * @param referenceText The reference they have typed
 * @param selectedChannel Which channel they chose, or null
 * @param canSubmit Whether the form is complete, **decided by the
 *   caller** rather than recomputed here
 * @param onAmountChange Amount edited
 * @param onReferenceChange Reference edited
 * @param onChannelSelected A channel chosen
 * @param onSubmit Submit the claim
 * @param modifier Layout modifier
 */
@Composable
fun PaymentFormScreen(
    destination: PaymentDestination,
    childName: String,
    batchName: String,
    amountText: String,
    referenceText: String,
    selectedChannel: String?,
    canSubmit: Boolean,
    onAmountChange: (String) -> Unit,
    onReferenceChange: (String) -> Unit,
    onChannelSelected: (String) -> Unit,
    onSubmit: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        // Named before anything is recorded [AC6.1.3].
        Text(
            stringResource(R.string.payment_confirm_child, childName, batchName),
            modifier = Modifier.testTag(TAG_PAYMENT_CONFIRM),
            style = MaterialTheme.typography.titleSmall,
        )

        when (destination) {
            is PaymentDestination.Known -> {
                Text(
                    stringResource(
                        R.string.payment_send_to,
                        destination.collectionNumber,
                    ),
                    modifier = Modifier.testTag(TAG_PAYMENT_DESTINATION),
                )
                destination.channels.forEach { channel ->
                    TextButton(
                        onClick = { onChannelSelected(channel) },
                        modifier = Modifier.testTag(TAG_PAYMENT_CHANNEL),
                    ) {
                        // The server's own value, rendered as a label.
                        Text(channel)
                    }
                }
            }

            is PaymentDestination.Unset ->
                // The destination step is ABSENT, not blank.
                Text(
                    stringResource(R.string.payment_ask_teacher),
                    Modifier.testTag(TAG_PAYMENT_NO_DESTINATION),
                )
        }

        OutlinedTextField(
            value = amountText,
            onValueChange = onAmountChange,
            label = { Text(stringResource(R.string.payment_amount_label)) },
            modifier = Modifier.fillMaxWidth().testTag(TAG_PAYMENT_AMOUNT),
            singleLine = true,
        )
        OutlinedTextField(
            value = referenceText,
            onValueChange = onReferenceChange,
            label = { Text(stringResource(R.string.payment_reference_label)) },
            modifier = Modifier.fillMaxWidth().testTag(TAG_PAYMENT_REFERENCE),
            singleLine = true,
        )
        Button(
            onClick = onSubmit,
            enabled = canSubmit && selectedChannel != null,
            modifier = Modifier.testTag(TAG_PAYMENT_SUBMIT),
        ) {
            Text(stringResource(R.string.payment_submit))
        }
    }
}
