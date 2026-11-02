package com.shikkhokplus.app.feature.dashboard.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.core.network.DashboardAttendanceMonthDto

/** One month's bar. */
const val TAG_DASHBOARD_ATTENDANCE_BAR: String = "dashboard_attendance_bar"

/** The full height of a bar at 100 percent. */
val ATTENDANCE_CHART_HEIGHT: Dp = 96.dp

private const val MAX_PERCENT = 100

/**
 * What a bar's server percent draws as.
 *
 * The percent is the server's; this only turns it into pixels. A month
 * with no held classes has no percent and draws no bar.
 *
 * @param percent The server's percent, or null
 * @param full The height at 100 percent
 * @return The bar's height
 */
fun attendanceBarHeight(
    percent: Int?,
    full: Dp,
): Dp = if (percent == null) 0.dp else full * (percent.coerceIn(0, MAX_PERCENT) / MAX_PERCENT.toFloat())

/**
 * Attendance by month, oldest first. The month containing today is
 * outlined with a dash rather than filled, because it is not finished.
 *
 * @param months The months, as the server sent them
 * @param modifier Layout modifier
 */
@Composable
fun AttendanceBars(
    months: List<DashboardAttendanceMonthDto>,
    modifier: Modifier = Modifier,
) {
    val fill = MaterialTheme.colorScheme.primary
    Row(
        modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceEvenly,
        verticalAlignment = Alignment.Bottom,
    ) {
        months.forEach { month ->
            val label = monthName(month.period)
            val spoken =
                month.percent?.let { stringResource(R.string.dashboard_bar_desc, label, Numerals.count(it)) }
                    ?: stringResource(R.string.dashboard_bar_none_desc, label)
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier =
                    Modifier
                        .testTag(TAG_DASHBOARD_ATTENDANCE_BAR)
                        .semantics(mergeDescendants = true) { contentDescription = spoken },
            ) {
                Text(
                    month.percent?.let { Numerals.count(it) } ?: "–",
                    style = MaterialTheme.typography.labelSmall,
                )
                Box(Modifier.height(ATTENDANCE_CHART_HEIGHT), contentAlignment = Alignment.BottomCenter) {
                    val height = attendanceBarHeight(month.percent, ATTENDANCE_CHART_HEIGHT)
                    if (month.inProgress) {
                        Canvas(Modifier.width(BAR_WIDTH).height(height)) {
                            val stroke = 2.dp.toPx()
                            drawRect(
                                color = fill,
                                topLeft = Offset(stroke / 2, stroke / 2),
                                size = Size(size.width - stroke, size.height - stroke),
                                style =
                                    Stroke(
                                        width = stroke,
                                        pathEffect = PathEffect.dashPathEffect(floatArrayOf(6.dp.toPx(), 4.dp.toPx())),
                                    ),
                            )
                        }
                    } else {
                        Box(
                            Modifier
                                .width(BAR_WIDTH)
                                .height(height)
                                .background(fill, RoundedCornerShape(topStart = 4.dp, topEnd = 4.dp)),
                        )
                    }
                }
                Text(label, style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}

private val BAR_WIDTH = 28.dp
