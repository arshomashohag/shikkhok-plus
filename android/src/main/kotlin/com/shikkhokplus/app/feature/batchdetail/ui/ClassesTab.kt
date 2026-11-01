package com.shikkhokplus.app.feature.batchdetail.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.format.YearMonth
import com.shikkhokplus.app.core.ui.CalendarDayUi
import com.shikkhokplus.app.core.ui.MonthCalendar
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.classcalendar.ClassCalendarUiState

/**
 * The Classes tab: the batch's month, drawn as the server decided it.
 *
 * Tapping a day with classes opens that class. Which screen opens is
 * the server's call, passed up unexamined.
 *
 * @param state The calendar's state
 * @param writeErrorKey Why adding a class failed, by message key, if it did
 * @param onPickMonth Called with the month the person moved to
 * @param onDay Called with a tapped day that has classes
 * @param onRetry Called to read the month again
 */
@Composable
fun ClassesTab(
    state: ClassCalendarUiState,
    writeErrorKey: String?,
    onPickMonth: (YearMonth) -> Unit,
    onDay: (CalendarDayUi) -> Unit,
    onRetry: () -> Unit,
) {
    when (state) {
        ClassCalendarUiState.Idle, ClassCalendarUiState.Loading -> SkeletonList(rows = 4)
        is ClassCalendarUiState.Failed ->
            ErrorCard(
                title = stringResource(R.string.batch_classes_failed),
                body = stringResource(MessageKeys.resolve(state.messageKey)),
                retryLabel = stringResource(R.string.roster_retry).takeIf { state.retryable },
                onRetry = onRetry.takeIf { state.retryable },
            )
        is ClassCalendarUiState.Loaded ->
            Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState())) {
                writeErrorKey?.let {
                    Banner(stringResource(MessageKeys.resolve(it)), tone = BannerTone.ERROR)
                }
                MonthCalendar(
                    year = state.view.month.year,
                    month = state.view.month.month,
                    days = state.view.days,
                    firstMonth = state.view.firstMonth,
                    lastMonth = state.view.lastMonth,
                    onPickMonth = onPickMonth,
                    onDay = onDay,
                    modifier = Modifier.padding(vertical = 8.dp),
                    today = state.view.today,
                )
                Column(Modifier.heightIn(min = 88.dp)) {}
            }
    }
}
