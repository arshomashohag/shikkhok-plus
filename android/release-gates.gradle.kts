// The two release-build gates team.md requires.
//
// **Why these are build tasks and not review items.** A reviewer
// looking at `implementation("com.example:analytics:1.2")` in a Gradle
// diff cannot know it pulls an SDK reading `Settings.Secure.ANDROID_ID`.
// Review cannot see what a transitive dependency collects, and on this
// project the reviewer is also still learning the platform [OC-3]. So
// the forbidden-identifier set is enforced mechanically or not at all.
//
// They run on the RELEASE variant only. A debug build can differ in
// which dependencies are present, and the release AAB is what ships.

// ---------------------------------------------------------------------
// Gate 1: the merged manifest declares exactly the approved permissions
// ---------------------------------------------------------------------
//
// Checks the MERGED manifest, not the source one. The source manifest is
// what we wrote; the merged manifest is what a transitive SDK has added
// to it, and the difference is the entire point.

val approvedPermissions = setOf(
    "android.permission.INTERNET",
)

// **Self-scoped permissions AndroidX defines on our own package.**
// These are not grants we request from the user: the name is prefixed
// with our applicationId, and they exist so a dynamically-registered
// receiver is not exported to other apps -- a hardening measure, the
// opposite of a privacy concern.
//
// Matched by SUFFIX against our package prefix rather than listed as
// literals, because the applicationId is part of the string.
val approvedSelfScopedSuffixes = setOf(
    ".DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION",
)

// Named explicitly rather than left to the allowlist, because the
// failure message matters. "AD_ID is present" tells you a Families
// policy violation is about to reach Play review; "unexpected
// permission" sends you reading manifest merger output.
val forbiddenPermissions = setOf(
    "com.google.android.gms.permission.AD_ID",
    "android.permission.READ_SMS",
    "android.permission.RECEIVE_SMS",
    "android.permission.READ_PHONE_STATE",
    "android.permission.READ_PHONE_NUMBERS",
    "android.permission.ACCESS_FINE_LOCATION",
    "android.permission.ACCESS_COARSE_LOCATION",
)

// **Named `verify*`, not `check*`.** AGP registers its OWN
// `checkReleaseManifest` in AbstractAppTaskManager.createCommonTasks,
// so that name collides with a built-in and fails configuration with
// "a task with that name already exists" -- which reads like a
// duplicate apply of this script and is not.
tasks.register("verifyReleasePermissions") {
    group = "verification"
    description = "The release manifest declares exactly the approved permissions"

    // **Several candidate paths, because AGP moves this.** The exact
    // location differs between AGP versions -- this project alone has
    // merged_manifest/.../processReleaseMainManifest and
    // merged_manifests/.../processReleaseManifest, differing by one
    // character. Hardcoding one means a silent gate after an upgrade,
    // so every known location is tried and NONE matching is a failure
    // rather than a pass.
    val manifestCandidates = listOf(
        "intermediates/merged_manifests/release/processReleaseManifest/AndroidManifest.xml",
        "intermediates/merged_manifest/release/processReleaseMainManifest/AndroidManifest.xml",
        "intermediates/packaged_manifests/release/processReleaseManifestForPackage/AndroidManifest.xml",
        "intermediates/bundle_manifest/release/processApplicationManifestReleaseForBundle/AndroidManifest.xml",
    )

    outputs.upToDateWhen { false }

    doLast {
        val file = manifestCandidates
            .map {
                layout.buildDirectory
                    .file(it)
                    .get()
                    .asFile
            }.firstOrNull { it.exists() }
            ?: throw GradleException(
                listOf(
                    "No merged manifest found. Looked in:",
                    manifestCandidates.joinToString("\n") { c -> "  - $c" },
                    "",
                    "This task must run AFTER the manifest is processed. If",
                    "AGP has moved it again, add the new path above rather",
                    "than removing the check -- a gate that cannot find its",
                    "input must FAIL, never pass.",
                ).joinToString("\n")
            )

        // Parsed as XML, not grepped. An earlier version of this check
        // matched the manifest's own COMMENT, which names AD_ID in
        // order to forbid it -- so it failed on the warning while
        // saying nothing about the thing.
        val doc = groovy.xml.XmlParser().parse(file)

        // Parsed as XML, not grepped. An earlier version of this check
        // matched the manifest's own COMMENT, which names AD_ID in
        // order to forbid it -- so it failed on the warning while
        // saying nothing about the thing.
        //
        // Typed explicitly: Groovy's XmlParser returns untyped nodes,
        // and an inferred Set<Any?> makes every use below ambiguous.
        val declared: Set<String> = doc
            .children()
            .filterIsInstance<groovy.util.Node>()
            .filter { node -> node.name().toString().endsWith("uses-permission") }
            .mapNotNull { node ->
                val attrs = node.attributes()
                val key = attrs.keys.firstOrNull { k ->
                    k.toString().endsWith("name")
                }
                key?.let { attrs[it]?.toString() }
            }.toSet()

        val forbidden = declared intersect forbiddenPermissions
        val selfScoped = declared
            .filter { p ->
                approvedSelfScopedSuffixes.any { s -> p.endsWith(s) }
            }.toSet()
        val unexpected =
            declared - approvedPermissions - forbiddenPermissions - selfScoped
        val problems = mutableListOf<String>()

        if (forbidden.isNotEmpty()) {
            val listed = forbidden.sorted().joinToString("\n") { p -> "  - $p" }
            problems += listOf(
                "FORBIDDEN permissions in the merged manifest:",
                listed,
                "",
                "AD_ID is the declaration Play's Families review looks",
                "for. A transitive ads or analytics SDK adds it",
                "silently via manifest merger. [TC-3, TC-6, D-37]",
            ).joinToString("\n")
        }
        if (unexpected.isNotEmpty()) {
            val listed = unexpected.sorted().joinToString("\n") { p -> "  - $p" }
            problems += listOf(
                "UNAPPROVED permissions in the merged manifest:",
                listed,
                "",
                "Something added these. Find which dependency, record",
                "an SDK admission note, and add it to",
                "approvedPermissions here only if it is genuinely",
                "wanted -- the allowlist is a decision, not a log.",
            ).joinToString("\n")
        }
        if (problems.isNotEmpty()) {
            throw GradleException("\n" + problems.joinToString("\n"))
        }

        logger.lifecycle(
            "Manifest gate: ${declared.size} permission(s), all approved " +
                "(${selfScoped.size} self-scoped)."
        )
    }
}

// ---------------------------------------------------------------------
// Gate 2: the minified DEX contains no forbidden framework reference
// ---------------------------------------------------------------------
//
// The allowlist above is insufficient alone: it catches an SDK that
// DECLARES AD_ID, while one reading ANDROID_ID or calling getImei
// declares no permission at all.
//
// Method references survive minification because they are framework
// calls -- R8 renames OUR symbols, never
// android.telephony.TelephonyManager.getImei.

val forbiddenIdentifiers = listOf(
    // Method references. These survive minification because they are
    // framework calls -- R8 renames OUR symbols, never
    // android.telephony.TelephonyManager.getImei.
    "getImei",
    "getSubscriberId",
    "getSimSerialNumber",
    "getLine1Number",
    "getSerial",
    "getMacAddress",
    "getBSSID",
    "getSSID",
    "AdvertisingIdClient",
    // **The VALUE, not the field name.** `Settings.Secure.ANDROID_ID`
    // is a compile-time String constant, so javac inlines it and the
    // identifier `ANDROID_ID` never reaches the DEX -- only its value,
    // the lowercase "android_id", does.
    //
    // Found by defect injection: a deliberate ANDROID_ID read was
    // added, the gate passed, and the DEX showed `ANDROID_ID` absent
    // while `android_id` was present. Listing the field name alone
    // meant this gate could never have caught the single most likely
    // identifier an SDK would read.
    "android_id",
)

tasks.register("verifyReleaseDex") {
    group = "verification"
    description = "The minified release DEX references no device identifier"

    outputs.upToDateWhen { false }

    doLast {
        val bundle = layout.buildDirectory
            .file("outputs/bundle/release/android-release.aab")
            .get()
            .asFile
        val apkDir = layout.buildDirectory
            .dir("outputs/apk/release")
            .get()
            .asFile

        // **Every release archive present, not the first one found.**
        // This preferred the AAB when both existed, which was correct
        // while the AAB was the only published artifact. Now that the
        // release also publishes an APK, picking one would leave the
        // other scanned only by inference -- same build type, same
        // minified DEX, therefore "it must be fine". That inference is
        // probably true and it is not a scan, and this gate's own
        // dexCount guard exists to refuse exactly that reasoning.
        val archives = buildList {
            if (bundle.exists()) add(bundle)
            apkDir.listFiles()
                ?.filter { it.name.endsWith(".apk") }
                ?.sortedBy { it.name }
                ?.let { addAll(it) }
        }

        if (archives.isEmpty()) {
            throw GradleException(
                "No release AAB or APK found. This gate must run after the\n" +
                    "release build, and must FAIL when it cannot find its input --\n" +
                    "a scan that finds nothing because it read nothing is worse\n" +
                    "than no scan, because it reports success."
            )
        }

        val hits = mutableMapOf<String, MutableList<String>>()
        var dexCount = 0

        // **Whole identifiers, not substrings.** A bare `contains`
        // reports `getSerial` inside `getSerialization` and
        // `getSerializedSize` -- which it did, on the very first run
        // of this gate, flagging protobuf and kotlinx.serialization
        // as device-identifier access.
        //
        // That matters more than the noise: a gate whose findings are
        // usually wrong gets switched off, and then the one real
        // finding never surfaces. The DEX string table stores each
        // identifier as its own NUL-length-prefixed entry, so a match
        // must not be flanked by another identifier character.
        val identifierChar = Regex("[A-Za-z0-9_$]")

        fun wholeMatch(
            text: String,
            id: String
        ): Boolean {
            var from = 0
            while (true) {
                val at = text.indexOf(id, from)
                if (at < 0) return false
                val before = if (at == 0) ' ' else text[at - 1]
                val afterIdx = at + id.length
                val after = if (afterIdx >= text.length) ' ' else text[afterIdx]
                val flanked =
                    identifierChar.matches(before.toString()) ||
                        identifierChar.matches(after.toString())
                if (!flanked) return true
                from = at + 1
            }
        }

        // **ZipInputStream over the local headers.** Either zip API
        // reads this archive correctly -- verified directly against
        // the AAB -- so the choice here is only that streaming avoids
        // holding the whole central directory.
        //
        // The dex count is asserted PER ARCHIVE, not across all of
        // them. A total would let a healthy AAB scan carry an APK that
        // yielded nothing, which is the "reports success having read
        // nothing" failure one archive further along.
        archives.forEach { archive ->
            var archiveDex = 0
            java.util.zip
                .ZipInputStream(
                    archive.inputStream().buffered()
                ).use { zis ->
                    while (true) {
                        val entry = zis.nextEntry ?: break
                        if (!entry.name.endsWith(".dex")) continue
                        archiveDex++
                        // The DEX string table stores identifiers as plain
                        // UTF-8, so a byte scan finds them without a dex
                        // parser. Latin-1 keeps byte offsets intact.
                        val text = zis.readBytes().toString(Charsets.ISO_8859_1)
                        forbiddenIdentifiers.forEach { id ->
                            if (wholeMatch(text, id)) {
                                hits.getOrPut(id) { mutableListOf() }
                                    .add(archive.name + "!" + entry.name)
                            }
                        }
                    }
                }

            if (archiveDex == 0) {
                throw GradleException(
                    "Scanned ${archive.name} and found NO .dex entries.\n" +
                        "The archive layout is not what this gate expects, so it\n" +
                        "checked nothing. Failing rather than reporting clean."
                )
            }
            dexCount += archiveDex
        }

        if (hits.isNotEmpty()) {
            val listed = hits.toSortedMap().entries.joinToString("\n") { e ->
                "  - " + e.key + "  (in " + e.value.joinToString(", ") + ")"
            }
            throw GradleException(
                listOf(
                    "",
                    "FORBIDDEN identifiers in the release DEX:",
                    listed,
                    "",
                    "project.md forbids transmitting ANY device or",
                    "advertising identifier [TC-3, TC-4, D-37, D-35].",
                    "A reference does not prove transmission, but it",
                    "proves something in the dependency graph CAN read",
                    "one -- which is the question Play's Data Safety",
                    "form asks. Find the dependency before shipping.",
                ).joinToString("\n")
            )
        }

        // Names the archives rather than only counting dex files: the
        // reader of a green log should be able to see WHICH artifacts
        // were covered, because the published set is what matters and
        // a count alone cannot distinguish one archive from two.
        logger.lifecycle(
            "DEX gate: $dexCount dex file(s) across " +
                archives.joinToString(", ") { it.name } +
                ", ${forbiddenIdentifiers.size} identifiers, none present."
        )
    }
}
