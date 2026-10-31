package com.shikkhokplus.app.core.designsystem

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.addPathNodes
import androidx.compose.ui.unit.dp

/**
 * The three role icons from the sign-up board (O1), as outline vectors.
 *
 * **Inline vectors, not Material icons**, for the reason the back arrow
 * gives: `material-icons-extended` is not a dependency, and adding it
 * would mean regenerating the Gradle lockfile and its checksums for
 * three icons. The path data is the board's own 24-unit SVG, with its
 * rectangles and circles written out as paths. Drawn in black and
 * tinted by `Icon`, so they follow the card's content colour.
 */
object RoleIcons {
    /** A board on a stand: the teacher. */
    val Teacher: ImageVector =
        outline(
            "Teacher",
            "M4.5 4h15a1.5 1.5 0 0 1 1.5 1.5v9a1.5 1.5 0 0 1-1.5 1.5h-15" +
                "a1.5 1.5 0 0 1-1.5-1.5v-9a1.5 1.5 0 0 1 1.5-1.5z",
            "M7 20h10M12 16v4M7 9h6M7 12h4",
        )

    /** A mortarboard: the student. */
    val Student: ImageVector =
        outline(
            "Student",
            "M2 9l10-5 10 5-10 5z",
            "M6 11v5c3 2 9 2 12 0v-5",
        )

    /** An adult beside a child: the guardian. */
    val Guardian: ImageVector =
        outline(
            "Guardian",
            "M6 7a3 3 0 1 0 6 0a3 3 0 1 0-6 0",
            "M14.8 10a2.2 2.2 0 1 0 4.4 0a2.2 2.2 0 1 0-4.4 0",
            "M3 20c0-4 3-6 6-6s6 2 6 6M14 20c0-2.5 1.5-4 3-4s3 1.5 3 4",
        )

    /**
     * Build one 24-unit outline icon from SVG path data.
     *
     * @param name The vector's name
     * @param paths Each path's SVG `d` attribute
     * @return The icon
     */
    private fun outline(name: String, vararg paths: String): ImageVector =
        ImageVector
            .Builder(
                name = name,
                defaultWidth = 24.dp,
                defaultHeight = 24.dp,
                viewportWidth = 24f,
                viewportHeight = 24f,
            ).apply {
                paths.forEach { d ->
                    addPath(
                        pathData = addPathNodes(d),
                        stroke = SolidColor(Color.Black),
                        strokeLineWidth = STROKE,
                        strokeLineCap = StrokeCap.Round,
                        strokeLineJoin = StrokeJoin.Round,
                    )
                }
            }.build()

    /** The board's stroke width, in viewport units. */
    private const val STROKE = 1.8f
}
