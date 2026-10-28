package com.shikkhokplus.app.core.designsystem

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.error
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp

/**
 * The design's text field (Components.dc.html, "Inputs").
 *
 * **The label sits above the box, not inside it.** M3's floating label
 * shrinks into the border as soon as the field is touched, which at 13sp
 * inside a 1dp line is hard to read in Bangla. The design puts a 14sp
 * SemiBold label above a white box with a 1.5dp border, 2dp in the
 * primary colour when focused and in the error colour when refused,
 * with help or error text under it.
 *
 * @param value The text
 * @param onValueChange Called with every edit
 * @param label The label above the box
 * @param modifier The layout modifier, applied to the whole field
 * @param help A line under the box, or null
 * @param error A refusal under the box, which also reddens the border
 * @param placeholder Shown while empty
 * @param prefix A fixed segment before the text, such as `+88`
 * @param enabled Whether it can be edited
 * @param singleLine One line, or a growing text area
 * @param minLines The text area's resting height in lines
 * @param keyboardType The keyboard to show
 * @param keyboardOptions Overrides [keyboardType] when given
 * @param keyboardActions What the keyboard's action key does
 * @param fieldModifier Applied to the editable text itself, for a test tag
 */
@Composable
fun ShikkhokTextField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    help: String? = null,
    error: String? = null,
    placeholder: String? = null,
    prefix: String? = null,
    enabled: Boolean = true,
    singleLine: Boolean = true,
    minLines: Int = 1,
    keyboardType: KeyboardType = KeyboardType.Text,
    keyboardOptions: KeyboardOptions? = null,
    keyboardActions: KeyboardActions = KeyboardActions.Default,
    fieldModifier: Modifier = Modifier,
) {
    val colors = MaterialTheme.colorScheme
    val interaction = remember { MutableInteractionSource() }
    val focused by interaction.collectIsFocusedAsState()
    val refused = error != null
    val borderColour = if (refused) colors.error else if (focused) colors.primary else colors.outline
    val borderWidth = if (refused || focused) 2.dp else 1.5.dp
    val shape = MaterialTheme.shapes.small
    val textStyle = MaterialTheme.typography.bodyLarge.copy(color = colors.onSurface)

    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, style = MaterialTheme.typography.labelLarge, color = colors.onSurface)
        BasicTextField(
            value = value,
            onValueChange = onValueChange,
            enabled = enabled,
            singleLine = singleLine,
            minLines = minLines,
            textStyle = textStyle,
            cursorBrush = SolidColor(colors.primary),
            interactionSource = interaction,
            keyboardOptions = keyboardOptions ?: KeyboardOptions(keyboardType = keyboardType),
            keyboardActions = keyboardActions,
            modifier =
                fieldModifier
                    .fillMaxWidth()
                    .semantics {
                        contentDescription = label
                        error?.let { error(it) }
                    },
            decorationBox = { inner ->
                Row(
                    Modifier
                        .fillMaxWidth()
                        .heightIn(min = FIELD_HEIGHT)
                        .background(colors.surface, shape)
                        .border(borderWidth, borderColour, shape),
                    verticalAlignment = if (singleLine) Alignment.CenterVertically else Alignment.Top,
                ) {
                    prefix?.let { PrefixSegment(it) }
                    Box(
                        Modifier
                            .weight(1f)
                            .padding(horizontal = 14.dp, vertical = if (singleLine) 0.dp else 10.dp),
                    ) {
                        if (value.isEmpty() && placeholder != null) {
                            Text(placeholder, style = textStyle.copy(color = colors.onSurfaceVariant))
                        }
                        inner()
                    }
                }
            },
        )
        FieldNote(help = help, error = error)
    }
}

/**
 * The line under a field: its refusal if there is one, else its help.
 *
 * @param help The help line, or null
 * @param error The refusal, or null
 */
@Composable
private fun FieldNote(help: String?, error: String?) {
    when {
        error != null ->
            Text(
                error,
                style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.SemiBold),
                color = MaterialTheme.colorScheme.error,
            )
        help != null ->
            Text(help, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

/**
 * A mobile-number field: the `+88` segment and a phone keyboard.
 *
 * @param value The number as typed
 * @param onValueChange Called with every edit
 * @param label The label above the box
 * @param modifier The layout modifier
 * @param help A line under the box, or null
 * @param error A refusal under the box, or null
 * @param enabled Whether it can be edited
 * @param fieldModifier Applied to the editable text, for a test tag
 */
@Composable
fun PhoneField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    help: String? = null,
    error: String? = null,
    enabled: Boolean = true,
    fieldModifier: Modifier = Modifier,
) {
    ShikkhokTextField(
        value = value,
        onValueChange = onValueChange,
        label = label,
        modifier = modifier,
        help = help,
        error = error,
        placeholder = PHONE_PLACEHOLDER,
        prefix = PHONE_PREFIX,
        enabled = enabled,
        keyboardType = KeyboardType.Phone,
        fieldModifier = fieldModifier,
    )
}

/**
 * The fixed segment at the start of a field.
 *
 * @param text What it shows
 */
@Composable
private fun PrefixSegment(text: String) {
    Row(
        Modifier
            .fillMaxHeight()
            .heightIn(min = FIELD_HEIGHT)
            .background(MaterialTheme.colorScheme.background, MaterialTheme.shapes.small)
            .padding(start = 14.dp, end = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(text, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    Box(
        Modifier
            .width(1.dp)
            .heightIn(min = FIELD_HEIGHT)
            .background(MaterialTheme.colorScheme.outlineVariant),
    )
}

/** The design's field height. */
private val FIELD_HEIGHT = 52.dp

/**
 * The country code shown before a Bangladeshi number. Decorative: the
 * person types the number as they know it and the server reads it in
 * every spelling.
 */
const val PHONE_PREFIX: String = "+88"

/** The shape of a number, shown while the field is empty. */
const val PHONE_PLACEHOLDER: String = "01XXX-XXXXXX"
