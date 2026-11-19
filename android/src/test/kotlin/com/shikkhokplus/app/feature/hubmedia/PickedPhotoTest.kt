package com.shikkhokplus.app.feature.hubmedia

import java.io.ByteArrayInputStream
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals

/** A picked file is read whole when small, and never far past the ceiling when its size was not reported. */
class PickedPhotoTest {

    @Test
    fun `a small file is read whole`() {
        val bytes = ByteArray(100_000) { it.toByte() }
        assertContentEquals(bytes, readAtMost(ByteArrayInputStream(bytes), MAX_UPLOAD_BYTES + 1))
    }

    @Test
    fun `reading stops one byte past the ceiling`() {
        val tooLarge = ByteArray(MAX_UPLOAD_BYTES.toInt() + 4096)
        val read = readAtMost(ByteArrayInputStream(tooLarge), MAX_UPLOAD_BYTES + 1)
        assertEquals(MAX_UPLOAD_BYTES + 1, read.size.toLong())
    }
}
