package com.shikkhokplus.app.feature.hubmedia

import android.content.ContentResolver
import android.net.Uri
import android.provider.OpenableColumns
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.io.InputStream

/**
 * A file the photo picker handed back, as the content resolver describes it.
 *
 * The bytes are read only when the upload starts, off the main thread,
 * and never more than one byte past the server's ceiling.
 *
 * @property contentType The type the resolver reports, or null
 * @property byteSize The size the resolver reports, or null when it cannot tell
 * @property read Reads the file; null or a throw means it could not be read
 */
class PickedPhoto(
    val contentType: String?,
    val byteSize: Long?,
    val read: suspend () -> ByteArray?,
)

/** The read buffer's size. */
private const val CHUNK: Int = 64 * 1024

/**
 * Describe a picked photo through the content resolver.
 *
 * @param resolver The app's content resolver
 * @param uri The picker's result
 * @return The photo; its bytes are read later
 */
fun pickedPhoto(resolver: ContentResolver, uri: Uri): PickedPhoto =
    PickedPhoto(
        contentType = resolver.getType(uri),
        byteSize = sizeOf(resolver, uri),
        read = {
            withContext(Dispatchers.IO) {
                resolver.openInputStream(uri)?.use { readAtMost(it, MAX_UPLOAD_BYTES + 1) }
            }
        },
    )

/**
 * The size the resolver reports, or null when the provider does not say.
 *
 * @param resolver The content resolver
 * @param uri The file
 * @return The size in bytes, or null
 */
private fun sizeOf(resolver: ContentResolver, uri: Uri): Long? =
    resolver.query(uri, arrayOf(OpenableColumns.SIZE), null, null, null)?.use { cursor ->
        val column = cursor.getColumnIndex(OpenableColumns.SIZE)
        if (column >= 0 && cursor.moveToFirst() && !cursor.isNull(column)) cursor.getLong(column) else null
    }

/**
 * Read a stream, stopping once [limit] bytes have been read, so a file
 * whose size the provider did not report cannot exhaust memory: anything
 * longer than the ceiling is refused as too large either way.
 *
 * @param input The stream
 * @param limit The most bytes to read
 * @return What was read, at most [limit] bytes
 */
internal fun readAtMost(input: InputStream, limit: Long): ByteArray {
    val out = ByteArrayOutputStream()
    val buffer = ByteArray(CHUNK)
    var total = 0L
    while (total < limit) {
        val n = input.read(buffer, 0, minOf(CHUNK.toLong(), limit - total).toInt())
        if (n < 0) break
        out.write(buffer, 0, n)
        total += n
    }
    return out.toByteArray()
}
