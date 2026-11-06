package com.shikkhokplus.app.core.session

import android.content.SharedPreferences
import androidx.compose.runtime.staticCompositionLocalOf
import com.shikkhokplus.app.core.network.WorkspaceDto
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** The app's workspace choice, for screens that switch or show it. */
val LocalWorkspaces = staticCompositionLocalOf<WorkspaceHolder?> { null }

/** The request header naming the workspace a teacher acts on. */
const val WORKSPACE_HEADER: String = "X-Workspace-Id"

/** Where the chosen workspace is kept between launches. */
interface WorkspaceStore {
    /**
     * Read the stored choice.
     *
     * @return The workspace's owner id, or null for the server's default
     */
    fun read(): String?

    /**
     * Keep a choice.
     *
     * @param ownerId The workspace's owner id, or null to forget it
     */
    fun write(ownerId: String?)
}

/** A store that lasts as long as the process; for tests and previews. */
class InMemoryWorkspaceStore(private var stored: String? = null) : WorkspaceStore {
    override fun read(): String? = stored

    override fun write(ownerId: String?) {
        stored = ownerId
    }
}

/**
 * The choice kept in shared preferences. An owner id is not a secret: it
 * grants nothing, and the server checks it against the account's own
 * workspaces on every request.
 *
 * @property preferences The preferences file
 */
class PreferencesWorkspaceStore(private val preferences: SharedPreferences) : WorkspaceStore {
    override fun read(): String? = preferences.getString(KEY, null)

    override fun write(ownerId: String?) {
        preferences.edit().apply { if (ownerId == null) remove(KEY) else putString(KEY, ownerId) }.apply()
    }

    private companion object {
        const val KEY = "workspace"
    }
}

/**
 * Which workspace the teacher screens act on: the account's own solo
 * workspace or a coaching centre it manages.
 *
 * **Never a grant.** The id travels as [WORKSPACE_HEADER] and the server
 * answers only for a workspace the account manages, refusing any other
 * value as it would no lens at all. The list offered here is the
 * server's own (`GET /v1/me`), so the switcher can offer nothing the
 * server would then refuse; a stored id the server no longer offers is
 * forgotten, and requests go without the header to the default.
 *
 * @property store Where the choice is kept
 */
class WorkspaceHolder(private val store: WorkspaceStore) {

    private val chosen = MutableStateFlow(store.read())

    /** The stored choice, or null for the server's default. */
    val state: StateFlow<String?> = chosen.asStateFlow()

    private val offeredFlow = MutableStateFlow<List<WorkspaceDto>>(emptyList())

    /** The workspaces the server last offered, solo first. */
    val offered: StateFlow<List<WorkspaceDto>> = offeredFlow.asStateFlow()

    /**
     * The header value for the next request.
     *
     * @return The chosen owner id, or null to send no header
     */
    fun current(): String? = chosen.value

    /**
     * The workspace in effect: the choice, else the server's first.
     *
     * @return The workspace, or null before the server has offered any
     */
    fun effective(): WorkspaceDto? =
        offeredFlow.value.firstOrNull { it.ownerId == chosen.value } ?: offeredFlow.value.firstOrNull()

    /**
     * Choose a workspace.
     *
     * @param ownerId The workspace, or null for the default
     */
    fun choose(ownerId: String?) {
        store.write(ownerId)
        chosen.value = ownerId
    }

    /**
     * Take the server's list, forgetting a choice it no longer offers.
     *
     * @param workspaces What `GET /v1/me` reported
     */
    fun reconcile(workspaces: List<WorkspaceDto>) {
        offeredFlow.value = workspaces
        val stored = chosen.value ?: return
        if (workspaces.none { it.ownerId == stored }) choose(null)
    }

    /** Forget everything, at sign-out. */
    fun clear() {
        offeredFlow.value = emptyList()
        choose(null)
    }
}

/**
 * The key offline copies are kept under: the account, and within it the
 * workspace, so a centre's cached screens never stand in for the solo
 * workspace's, or one centre's for another's.
 *
 * Kept under the account's own prefix, so clearing an account's copies
 * still clears every workspace's.
 *
 * @param account The signed-in account, or null
 * @param workspace The chosen workspace, or null for the default
 * @return The scope, or null when nobody is signed in
 */
fun offlineScope(account: String?, workspace: String?): String? =
    account?.let { if (workspace == null) it else "$it/ws-$workspace" }
