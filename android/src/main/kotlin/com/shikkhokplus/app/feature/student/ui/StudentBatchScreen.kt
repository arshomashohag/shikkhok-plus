package com.shikkhokplus.app.feature.student.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.TabRowDefaults
import androidx.compose.material3.TabRowDefaults.tabIndicatorOffset
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.designsystem.asHeading
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.core.format.shortDate
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.student.FamilyTab
import com.shikkhokplus.app.feature.student.FeeLine
import com.shikkhokplus.app.core.format.YearMonth
import com.shikkhokplus.app.core.ui.CalendarClassUi
import com.shikkhokplus.app.feature.classcalendar.ClassCalendarUiState
import com.shikkhokplus.app.feature.student.StudentBatchUiState
import com.shikkhokplus.app.feature.student.NextClass
import com.shikkhokplus.app.feature.student.StudentBatchView
import com.shikkhokplus.app.core.format.dayLabel
import com.shikkhokplus.app.core.ui.displayTime

/** The loading placeholder. */
const val TAG_STUDENT_BATCH_LOADING: String = "student_batch_loading"

/** The next-class card. */
const val TAG_STUDENT_NEXT_CLASS: String = "student_next_class"

/** One tab of the batch. */
const val TAG_FAMILY_TAB: String = "family_tab"

/** The fee-history link. */
const val TAG_STUDENT_FEES: String = "student_fees"

/** The link to the progress dashboard. */
const val TAG_STUDENT_PROGRESS: String = "student_progress"

/** The failure message. */
const val TAG_STUDENT_BATCH_ERROR: String = "student_batch_error"

/**
 * What the family batch screen's taps do.
 *
 * @property onOpenClass Open a class's detail
 * @property onPickMonth Move the Classes calendar to a month
 * @property onRetryMonth Read the Classes calendar's month again
 * @property onOpenExam Open a done exam's marksheet, by exam id
 * @property onOpenExamDetail Open an upcoming exam's detail, by exam id
 * @property onOpenNotice Open a notice's detail, by notice id
 */
data class FamilyOpeners(
    val onOpenClass: (CalendarClassUi) -> Unit = {},
    val onPickMonth: (YearMonth) -> Unit = {},
    val onRetryMonth: () -> Unit = {},
    val onOpenExam: (String) -> Unit = {},
    val onOpenExamDetail: (String) -> Unit = {},
    val onOpenNotice: (String) -> Unit = {},
)

/**
 * S2: one batch from the student's or a guardian's side, in tabs.
 *
 * The fee stays in the header; Classes, Exams, Notices and Teacher
 * are the tabs. Everything shown is what the server decided; the
 * screen formats and decides nothing [TC-9].
 *
 * @param state What to render
 * @param onBack Called to leave
 * @param onOpenFees Called to open the fee history
 * @param onRetry Called when the reader asks to try again
 * @param modifier The layout modifier
 * @param onPay Called to pay this batch's fee (S3)
 * @param tab The open tab
 * @param onSelect Called with a tab
 * @param openers What tapping a class, exam or notice does
 * @param calendar The Classes tab's month
 * @param onOpenProgress Opens this seat's progress dashboard
 */
@Composable
fun StudentBatchScreen(
    state: StudentBatchUiState,
    onBack: () -> Unit,
    onOpenFees: () -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
    onPay: () -> Unit = {},
    tab: FamilyTab = FamilyTab.CLASSES,
    onSelect: (FamilyTab) -> Unit = {},
    openers: FamilyOpeners = FamilyOpeners(),
    calendar: ClassCalendarUiState = ClassCalendarUiState.Idle,
    onOpenProgress: (() -> Unit)? = null,
) {
    val batch = (state as? StudentBatchUiState.Loaded)?.view?.batch
    ListScreenScaffold(
        title = batch?.batchName?.let(Numerals::freeText) ?: stringResource(R.string.my_batches_title),
        subtitle = (batch?.childName ?: batch?.teacherName)?.let(Numerals::freeText),
        modifier = modifier,
        onBack = onBack,
        header = {
            if (state is StudentBatchUiState.Loaded) {
                if (state.offline) OfflineBanner(R.string.family_offline_body)
                BatchHeader(state.view, onOpenFees, onPay, onOpenProgress, offline = state.offline)
                FamilyTabs(tab, onSelect)
            }
        },
    ) {
        when (state) {
            StudentBatchUiState.Loading ->
                SkeletonList(rows = 3, modifier = Modifier.testTag(TAG_STUDENT_BATCH_LOADING))
            is StudentBatchUiState.Loaded ->
                Column(
                    Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(top = 8.dp, bottom = 24.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) { FamilyTabBody(tab, state.view, openers, calendar) }
            is StudentBatchUiState.Failed -> {
                Text(
                    stringResource(MessageKeys.resolve(state.messageKey)),
                    Modifier.testTag(TAG_STUDENT_BATCH_ERROR),
                )
                if (state.retryable) {
                    Button(onClick = onRetry) { Text(stringResource(R.string.roster_retry)) }
                }
            }
        }
    }
}

/**
 * What stays above the tabs on every one: the subjects, the next
 * class and the fee with its Pay action.
 *
 * @param view The batch
 * @param onOpenFees Called to open the fee history
 * @param onPay Called to pay this batch's fee
 * @param onOpenProgress Opens the progress dashboard, or null
 * @param offline Whether this is the session's earlier copy
 */
@Composable
private fun BatchHeader(
    view: StudentBatchView,
    onOpenFees: () -> Unit,
    onPay: () -> Unit,
    onOpenProgress: (() -> Unit)?,
    offline: Boolean = false,
) {
    if (view.teacher.subjects.isNotEmpty()) {
        Quiet(view.teacher.subjects.joinToString(" · ") { Numerals.freeText(it) })
    }
    val next = view.next
    if (next == null) {
        ShikkhokCard(Modifier.testTag(TAG_STUDENT_NEXT_CLASS)) {
            Text(stringResource(R.string.student_no_next_class), color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    } else {
        NextClassHero(
            next,
            thenLine(view.following),
            withEnd = true,
            modifier = Modifier.testTag(TAG_STUDENT_NEXT_CLASS),
        )
    }
    // **No fee status that cannot be confirmed** (S2 offline): a payment
    // may have been approved since this copy was read.
    if (offline) {
        ShikkhokCard(Modifier.testTag(TAG_STUDENT_FEE_UNAVAILABLE)) {
            Text(
                stringResource(R.string.family_fee_unavailable),
                style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.SemiBold),
            )
            Quiet(stringResource(R.string.family_fee_unavailable_body))
        }
        return
    }
    view.batch.fee?.let { fee -> FeeCard(fee, onOpenFees, onPay) }
        ?: TextButton(onClick = onOpenFees, modifier = Modifier.testTag(TAG_STUDENT_FEES)) {
            Text(stringResource(R.string.screen_title_fee_history))
        }
    if (onOpenProgress != null) {
        TextButton(onClick = onOpenProgress, modifier = Modifier.testTag(TAG_STUDENT_PROGRESS)) {
            Text(stringResource(R.string.dashboard_open_progress))
        }
    }
}

/**
 * "Then Mon 19 Oct, Wed 21 Oct (moved to 6:00 pm)", or null with none.
 *
 * @param following The classes after the next
 * @return The line
 */
@Composable
private fun thenLine(following: List<NextClass>): String? {
    if (following.isEmpty()) return null
    val days =
        following.map { next ->
            if (next.moved) {
                stringResource(R.string.student_moved_to, dayLabel(next.date), displayTime(next.startTime))
            } else {
                dayLabel(next.date)
            }
        }
    return stringResource(R.string.student_then, days.joinToString(", "))
}

/**
 * The four tabs, with the open one underlined in the primary colour.
 *
 * @param tab The open tab
 * @param onSelect Called with a tab
 */
@Composable
private fun FamilyTabs(tab: FamilyTab, onSelect: (FamilyTab) -> Unit) {
    TabRow(
        selectedTabIndex = tab.ordinal,
        containerColor = MaterialTheme.colorScheme.background,
        contentColor = MaterialTheme.colorScheme.primary,
        indicator = { positions ->
            TabRowDefaults.SecondaryIndicator(
                Modifier.tabIndicatorOffset(positions[tab.ordinal]),
                height = 3.dp,
                color = MaterialTheme.colorScheme.primary,
            )
        },
    ) {
        FamilyTab.entries.forEach { each ->
            Tab(
                selected = each == tab,
                onClick = { onSelect(each) },
                selectedContentColor = MaterialTheme.colorScheme.primary,
                unselectedContentColor = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.heightIn(min = 48.dp).testTag(TAG_FAMILY_TAB),
            ) {
                Text(
                    stringResource(tabLabel(each)),
                    style = MaterialTheme.typography.titleSmall,
                    maxLines = 1,
                    softWrap = false,
                    modifier = Modifier.padding(horizontal = 4.dp, vertical = 12.dp),
                )
            }
        }
    }
}

/**
 * A tab's name.
 *
 * @param tab The tab
 * @return Its string resource
 */
private fun tabLabel(tab: FamilyTab): Int =
    when (tab) {
        FamilyTab.CLASSES -> R.string.batch_tab_classes
        FamilyTab.EXAMS -> R.string.batch_tab_exams
        FamilyTab.NOTICES -> R.string.batch_tab_notices
        FamilyTab.TEACHER -> R.string.family_tab_teacher
    }

/**
 * The open tab's body.
 *
 * @param tab The open tab
 * @param view The batch
 * @param openers What the taps do
 * @param calendar The Classes tab's month
 */
@Composable
private fun ColumnScope.FamilyTabBody(
    tab: FamilyTab,
    view: StudentBatchView,
    openers: FamilyOpeners,
    calendar: ClassCalendarUiState,
) {
    when (tab) {
        FamilyTab.CLASSES -> ClassesTab(calendar, openers.onPickMonth, openers.onOpenClass, openers.onRetryMonth)
        FamilyTab.EXAMS -> ExamsTab(view, openers.onOpenExam, openers.onOpenExamDetail)
        FamilyTab.NOTICES -> NoticesTab(view, openers.onOpenNotice)
        FamilyTab.TEACHER -> TeacherTab(view.teacher)
    }
}

/**
 * "October fee · ৳1,200", when it was paid or is due, and its chip; a
 * pay action while it is owed and not being checked.
 *
 * @param fee The period
 * @param onOpen Called to open the fee history
 * @param onPay Called to pay it
 */
@Composable
private fun FeeCard(fee: FeeLine, onOpen: () -> Unit, onPay: () -> Unit) {
    ShikkhokCard(onClick = onOpen, modifier = Modifier.testTag(TAG_STUDENT_FEES)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                val month = monthName(fee.period, short = false)
                Text(
                    fee.charged?.let { stringResource(R.string.student_fee_month_amount, month, Numerals.money(it)) }
                        ?: stringResource(R.string.student_fee_month, month),
                    style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.SemiBold),
                )
                Quiet(
                    fee.paidOn?.let { stringResource(R.string.student_paid_on, shortDate(it)) }
                        ?: stringResource(R.string.student_due_by, shortDate(fee.dueDate)),
                )
            }
            FeeChip(fee)
        }
        if (!fee.verifying && fee.statusKey in PAYABLE_KEYS) {
            TextAction(stringResource(R.string.student_pay_this), onPay, Modifier.testTag(TAG_STUDENT_PAY))
        }
    }
}

/**
 * A section heading, 14/22 bold in the board's grey.
 *
 * @param text The heading
 */
@Composable
internal fun Section(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(top = 6.dp).asHeading(),
    )
}

/**
 * A quiet secondary line.
 *
 * @param text The line
 */
@Composable
internal fun Quiet(text: String) {
    Text(text, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

/**
 * A white card holding rows.
 *
 * @param content The rows
 */
@Composable
internal fun RowsCard(content: @Composable ColumnScope.() -> Unit) {
    Column(
        Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium),
        content = content,
    )
}

/** The divider between rows, inset from the left as the boards draw it. */
@Composable
internal fun InsetDivider() {
    HorizontalDivider(Modifier.padding(start = 16.dp), color = MaterialTheme.colorScheme.surfaceContainerHigh)
}

/** A short value set in semibold, as the boards' dates are. */
internal val Emphasis
    @Composable get() = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold)

/** The statuses a student can pay toward, as the fee mapper names them. */
private val PAYABLE_KEYS = setOf("fees.status.unpaid", "fees.status.partly_paid")

/** The fee card's stand-in while offline. */
const val TAG_STUDENT_FEE_UNAVAILABLE: String = "student_fee_unavailable"

/** The "Pay this fee" action. */
const val TAG_STUDENT_PAY: String = "student_pay"

/**
 * The offline banner on a family screen: this is the session's earlier
 * copy, and what needs a connection waits for one.
 *
 * @param body The string resource saying what still works
 */
@Composable
internal fun OfflineBanner(body: Int) {
    Banner(
        title = stringResource(R.string.offline_title),
        body = stringResource(body),
        tone = BannerTone.NEUTRAL,
        modifier = Modifier.testTag(TAG_FAMILY_OFFLINE),
    )
}

/** The offline banner on a family screen. */
const val TAG_FAMILY_OFFLINE: String = "family_offline"
