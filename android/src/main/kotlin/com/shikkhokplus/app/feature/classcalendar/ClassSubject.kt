package com.shikkhokplus.app.feature.classcalendar

import com.shikkhokplus.app.core.network.SubjectOptionDto
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.record.RecordRepository

/** The most a class's topics or notes may hold, as the server's schema states. */
const val CLASS_TEXT_MAX: Int = 2000

/**
 * Cut typed text to what the server accepts, so the field never holds
 * more than a Save could send.
 *
 * @param typed The text as typed
 * @return At most [CLASS_TEXT_MAX] characters of it
 */
fun capClassText(typed: String): String = typed.take(CLASS_TEXT_MAX)

/** How setting a class's subject went. */
sealed interface SubjectSave {
    /** Nothing to change: no choice, or the class already has it. */
    data object Unchanged : SubjectSave

    /**
     * The server has the new subject.
     *
     * @property name Its name, now the class's subject
     */
    data class Saved(val name: String) : SubjectSave

    /**
     * The server refused, or could not be reached.
     *
     * @property messageKey Why, by message key
     */
    data class Failed(val messageKey: String) : SubjectSave
}

/**
 * The subject choice on a class screen, through the same online-only
 * write the record sheet uses (`setSubject`); the server decides
 * whether the class may take it.
 *
 * @property records Where subjects are read and set
 */
class ClassSubjects(private val records: RecordRepository) {

    /**
     * Read a batch's subjects for the chooser.
     *
     * @param batchId The batch
     * @return Its subjects, or none when they cannot be read
     */
    suspend fun load(batchId: String): List<SubjectOptionDto> =
        (records.subjects(batchId) as? AuthResult.Ok)?.value.orEmpty()

    /**
     * Set the chosen subject, if it differs from the class's own.
     *
     * @param sessionId The class
     * @param subjects The batch's subjects
     * @param chosenId The chosen subject, or null
     * @param currentName The class's subject now, or null
     * @return How it went
     */
    suspend fun saveIfChanged(
        sessionId: String,
        subjects: List<SubjectOptionDto>,
        chosenId: String?,
        currentName: String?,
    ): SubjectSave {
        val chosen = subjects.firstOrNull { it.id == chosenId } ?: return SubjectSave.Unchanged
        if (chosen.name == currentName) return SubjectSave.Unchanged
        return when (val result = records.setSubject(sessionId, chosen.id)) {
            is AuthResult.Ok -> SubjectSave.Saved(chosen.name)
            is AuthResult.Refused -> SubjectSave.Failed(result.envelope.error.messageKey)
            AuthResult.TransportFailure -> SubjectSave.Failed(ClassCalendarViewModel.OFFLINE_KEY)
        }
    }
}
