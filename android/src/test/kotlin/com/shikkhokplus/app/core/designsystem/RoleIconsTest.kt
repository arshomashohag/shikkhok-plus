package com.shikkhokplus.app.core.designsystem

import androidx.compose.ui.graphics.vector.VectorGroup
import androidx.compose.ui.graphics.vector.VectorPath
import androidx.compose.ui.unit.dp
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The sign-up board's three role icons, built from its SVG path data.
 *
 * A path string that fails to parse builds an icon with no nodes, which
 * draws nothing and fails no screen test, so the paths are asserted here.
 */
class RoleIconsTest {

    private fun pathsOf(group: VectorGroup): List<VectorPath> = group.filterIsInstance<VectorPath>()

    @Test
    fun `every icon is a 24-unit outline at 24dp`() {
        listOf(RoleIcons.Teacher, RoleIcons.Student, RoleIcons.Guardian).forEach { icon ->
            assertEquals(24.dp, icon.defaultWidth)
            assertEquals(24f, icon.viewportWidth)
            assertTrue(pathsOf(icon.root).all { it.pathData.isNotEmpty() && it.stroke != null })
        }
    }

    @Test
    fun `each icon carries every shape the board draws`() {
        assertEquals(2, pathsOf(RoleIcons.Teacher.root).size)
        assertEquals(2, pathsOf(RoleIcons.Student.root).size)
        assertEquals(3, pathsOf(RoleIcons.Guardian.root).size)
    }
}
