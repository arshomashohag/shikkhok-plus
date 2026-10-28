package com.shikkhokplus.app.feature.batchdetail.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.network.BatchEdit
import com.shikkhokplus.app.core.ui.BatchCreateForm
import com.shikkhokplus.app.core.ui.BatchFormValues
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.batchdetail.BatchHeader

/** The edit form. */
const val TAG_EDIT_BATCH: String = "edit_batch"

/**
 * Edit a batch's name, subjects, fee and due day.
 *
 * The same fields as creating one, filled in. Class days are left to the
 * batch's own schedule screen. A new fee reaches only months not yet
 * charged; the server decides that, not this form.
 *
 * @param header The batch as it stands
 * @param write Where the save stands
 * @param onSave Called with what changed
 * @param onClose Called to leave, saved or not
 * @param modifier The layout modifier
 */
@Composable
fun EditBatchScreen(
    header: BatchHeader,
    write: WriteState,
    onSave: (BatchEdit) -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
) {
    LaunchedEffect(write) {
        if (write == WriteState.Saved) onClose()
    }
    ScreenScaffold(
        title = stringResource(R.string.batch_edit_title),
        modifier = modifier,
        onBack = onClose,
    ) {
        BatchCreateForm(
            onCreate = { name, subjects, fee, dueDay, _ ->
                onSave(BatchEdit(name = name, subjects = subjects, defaultFee = fee, feeDueDay = dueDay))
            },
            onCancel = onClose,
            modifier = Modifier.testTag(TAG_EDIT_BATCH),
            saving = write == WriteState.Saving,
            error = (write as? WriteState.Failed)?.let { stringResource(MessageKeys.resolve(it.messageKey)) },
            initial =
                BatchFormValues(
                    name = header.name,
                    subjects = header.subjects.joinToString(", "),
                    fee = header.defaultFee?.toString().orEmpty(),
                    dueDay = header.feeDueDay?.toString().orEmpty(),
                ),
            withSchedule = false,
            submitLabel = stringResource(R.string.batch_edit_save),
        )
    }
}
