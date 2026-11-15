package com.shikkhokplus.app.core.ui

import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.autofill.AutofillNode
import androidx.compose.ui.autofill.AutofillType
import androidx.compose.ui.composed
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.layout.boundsInWindow
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalAutofill
import androidx.compose.ui.platform.LocalAutofillTree

/** What a field holds, for the platform's autofill service. */
enum class AutofillHint {
    /** An email address. */
    EMAIL,

    /** An existing password, to fill. */
    PASSWORD,

    /** A password being chosen, to generate and save. */
    NEW_PASSWORD,

    /**
     * An existing username, to fill: the sign-in field and the
     * choose-username gate [TSD-4]. Nothing is read from the SIM.
     */
    USERNAME,

    /** A username being created, to save: sign-up, the replacement and rename [TSD-4]. */
    NEW_USERNAME,
}

/**
 * The platform's autofill type for a hint.
 *
 * Pure, and outside the composable, so the mapping is unit-tested.
 *
 * @param hint What the field holds
 * @return The type the autofill service is told
 */
@OptIn(ExperimentalComposeUiApi::class)
internal fun autofillTypeOf(hint: AutofillHint): AutofillType =
    when (hint) {
        AutofillHint.EMAIL -> AutofillType.EmailAddress
        AutofillHint.PASSWORD -> AutofillType.Password
        AutofillHint.NEW_PASSWORD -> AutofillType.NewPassword
        AutofillHint.USERNAME -> AutofillType.Username
        AutofillHint.NEW_USERNAME -> AutofillType.NewUsername
    }

/**
 * Let the platform's autofill service (a password manager) fill, or
 * offer to save, this field.
 *
 * **The Compose 1.7 way**, which this project's BOM pins: an
 * [AutofillNode] registered in the [LocalAutofillTree], positioned from
 * the layout, and requested when the field takes focus. From Compose 1.8
 * the same is a `contentType` semantics property; when the BOM moves,
 * this helper is the one place to change, which is also why the
 * experimental API's opt-in stays inside it.
 *
 * Nothing here reads anything from the device: the autofill service
 * offers what the person saved, and only into a field they focused.
 *
 * @param hint What the field holds
 * @param onFill Called with the value the person picked
 * @return The modifier
 */
@OptIn(ExperimentalComposeUiApi::class)
fun Modifier.autofill(
    hint: AutofillHint,
    onFill: (String) -> Unit,
): Modifier =
    composed {
        val autofill = LocalAutofill.current
        val tree = LocalAutofillTree.current
        val fill by rememberUpdatedState(onFill)
        val node =
            remember(hint) {
                AutofillNode(autofillTypes = listOf(autofillTypeOf(hint)), onFill = { fill(it) })
            }
        DisposableEffect(node) {
            tree += node
            onDispose { tree.children.remove(node.id) }
        }
        this
            .onGloballyPositioned { node.boundingBox = it.boundsInWindow() }
            .onFocusChanged { focus ->
                // A field focused before its first layout has no bounds to
                // show the suggestion against, and the platform refuses it.
                autofill?.run {
                    when {
                        focus.isFocused && node.boundingBox != null -> requestAutofillForNode(node)
                        !focus.isFocused -> cancelAutofillForNode(node)
                    }
                }
            }
    }
