// ---------------------------------------------------------------------------
// Kotlin coverage, and the no-regression ratchet.
//
// **Why a ratchet and not a percentage floor.** `team.md` is explicit that
// the Android surface carries named obligations and NO percentage target,
// and the reasoning is worth restating because it is easy to mistake for
// laziness: gating a surface the reviewer cannot yet evaluate produces tests
// written to raise a number, and a test written to raise a number certifies
// nothing. That is an argument against inventing a TARGET, not against
// measuring the TREND -- so coverage is reported from the first Android Bolt,
// and once three have merged, no decrease is permitted.
//
// Three have merged: auth, batches, roster. The ratchet is therefore live
// from today rather than deferred again.
//
// The recorded floor lives in `android/coverage-floor.txt`, committed, and
// moves only upward and only by a deliberate commit. A build that improves
// coverage prints the new figure and tells you to raise it; it does not
// raise it silently, because a self-raising ratchet records whatever the
// last run happened to produce, including a run that skipped tests.
// ---------------------------------------------------------------------------

plugins.apply("jacoco")

extensions.configure<JacocoPluginExtension>("jacoco") {
    toolVersion = "0.8.12"
}

val coverageFloorFile = file("coverage-floor.txt")

// Generated and framework code is excluded. These are not "code we chose not
// to test" -- they are code nobody wrote, and counting them moves the figure
// without changing what is verified.
val coverageExclusions = listOf(
    "**/R.class",
    "**/R$*.class",
    "**/BuildConfig.*",
    "**/Manifest*.*",
    "**/*Test*.*",
    "android/**/*.*",
    // Compose generates substantial synthetic code per composable. Including
    // it would make the figure track how many screens exist rather than how
    // much logic is covered -- and the ViewModel state machines and the
    // response-to-UiState mapping functions ARE the stated test targets
    // [team: Testing Posture].
    "**/*\$\$inlined\$*",
    "**/ComposableSingletons*",
    "**/*_Factory*",
    "**/Hilt_*",
    // **The composables themselves, for the same stated reason.**
    //
    // *(Corrected 2026-10-23, D1.)* The three exclusions above catch
    // Compose's synthetic artifacts and not the `@Composable` functions,
    // so every screen counted as a block of permanently-uncovered lines.
    // JaCoCo instruments the class but Robolectric drives the composition
    // through Compose's runtime, so the screen's own bytecode records no
    // hits even when a Compose test exercises it: `AuthScreenKt` measured
    // 60 missed and 0 covered while `AuthScreenTest` passed. Across the
    // module that was 573 of 1769 lines -- a third of the denominator --
    // and it moved with how many screens existed rather than with what
    // was verified, which is exactly what the comment above says the
    // exclusions exist to prevent.
    //
    // The screens are NOT untested. `*ScreenTest` classes run on every
    // commit under Robolectric and assert what each state renders,
    // including the rules that are only observable as absences: that the
    // already-added notice names no teacher, that the two decline sheets
    // say opposite things about the fee, that the profile edit offers no
    // deletion control. Those tests are the verification; this figure
    // never was.
    "**/*ScreenKt*",
    "**/ui/*Kt*",
    // **The navigation graph, for exactly the same reason.**
    //
    // *(Added 2026-10-26.)* `ShikhokNavHost` is a `@Composable` that
    // happens to live in `navigation/` rather than `ui/`, so the two
    // globs above miss it and JaCoCo counted 127 lines it can never
    // record a hit against — dropping the module from 60.39% to
    // 57.20% on a change that removed no test.
    //
    // The graph is NOT unverified. `DestinationTest` asserts the route
    // patterns and their argument encoding, which is the part that can
    // actually be wrong: a route built by string interpolation at a
    // call site is how a route and its argument name drift apart. What
    // the composable adds beyond that is wiring Compose cannot measure
    // from bytecode.
    "**/navigation/*Kt*",
)

tasks.register<JacocoReport>("jacocoDebugReport") {
    group = "verification"
    description = "Kotlin coverage for the debug unit tests."
    dependsOn("testDebugUnitTest")

    reports {
        xml.required.set(true)
        html.required.set(true)
        csv.required.set(false)
    }

    classDirectories.setFrom(
        fileTree("${layout.buildDirectory.get()}/tmp/kotlin-classes/debug") {
            exclude(coverageExclusions)
        },
    )
    sourceDirectories.setFrom(files("src/main/kotlin"))
    // **Scoped to the jacoco output directory, not the whole build tree.**
    // A `fileTree` over `build/` makes this task an implicit consumer of
    // every other task's output -- Gradle detects that as an undeclared
    // dependency on `lintAnalyzeDebug` and fails the build, correctly:
    // without an ordering rule the report could be generated before or
    // after lint and produce different results. Caught by running the full
    // gate rather than the task alone.
    executionData.setFrom(
        file("${layout.buildDirectory.get()}/jacoco/testDebugUnitTest.exec"),
    )
}

// ---------------------------------------------------------------------------
// The ratchet itself.
//
// Reads the committed floor, reads the generated report, compares, and fails
// on a decrease. It does NOT fail on a low absolute number -- that is the
// point of a ratchet rather than a floor.
// ---------------------------------------------------------------------------
tasks.register("verifyCoverageRatchet") {
    group = "verification"
    description = "Fails if Kotlin line coverage dropped below the committed floor."
    dependsOn("jacocoDebugReport")

    doLast {
        val reportFile = file(
            "${layout.buildDirectory.get()}/reports/jacoco/jacocoDebugReport/jacocoDebugReport.xml",
        )

        // **Guard the guard.** A ratchet that cannot find its report must
        // fail loudly: reporting "coverage did not drop" having measured
        // nothing is exactly the vacuous-gate shape this project has already
        // been bitten by twice -- the shallow-clone secrets scan and the
        // two contract gates that passed against zero routes.
        if (!reportFile.exists()) {
            throw GradleException(
                buildString {
                    appendLine("Coverage ratchet: no report at ${reportFile.path}.")
                    appendLine("The ratchet did NOT run. This is a failure, not a skip:")
                    appendLine("a gate that cannot measure must not report success.")
                },
            )
        }

        // JaCoCo's XML carries a DTD reference it tries to fetch; disable
        // external entity resolution rather than reaching the network
        // during a build.
        val factory = javax.xml.parsers.DocumentBuilderFactory.newInstance().apply {
            setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false)
            isValidating = false
        }
        val doc = factory.newDocumentBuilder().parse(reportFile)

        // The report's LAST top-level <counter type="LINE"> is the total.
        val counters = doc.documentElement.childNodes
        var covered = 0
        var missed = 0
        for (i in 0 until counters.length) {
            val node = counters.item(i)
            if (node.nodeName != "counter") continue
            val attrs = node.attributes ?: continue
            if (attrs.getNamedItem("type")?.nodeValue != "LINE") continue
            covered = attrs.getNamedItem("covered")?.nodeValue?.toIntOrNull() ?: 0
            missed = attrs.getNamedItem("missed")?.nodeValue?.toIntOrNull() ?: 0
        }

        val total = covered + missed
        if (total == 0) {
            throw GradleException(
                buildString {
                    appendLine("Coverage ratchet: the report counts ZERO lines.")
                    appendLine("Either no classes were analysed or the exclusion")
                    appendLine("list swallowed everything. Measuring nothing is")
                    appendLine("not the same as passing.")
                },
            )
        }

        val pct = covered * 100.0 / total
        val floor = if (coverageFloorFile.exists()) {
            coverageFloorFile.readText().trim().toDoubleOrNull() ?: 0.0
        } else {
            0.0
        }

        val rounded = String.format("%.2f", pct)
        println("Kotlin line coverage: $rounded% ($covered/$total lines)")
        println("Committed floor:      $floor%")

        // A small tolerance, because the figure moves slightly with
        // unrelated compiler output and a ratchet that fires on 0.01% is a
        // ratchet people disable.
        if (pct < floor - 0.5) {
            throw GradleException(
                buildString {
                    appendLine("Kotlin coverage DROPPED: $rounded% against a floor of $floor%.")
                    appendLine()
                    appendLine("The ratchet permits no decrease once three Android")
                    appendLine("Bolts have merged. Either cover the new code, or -- if")
                    appendLine("the drop is genuinely correct -- lower the number in")
                    appendLine("android/coverage-floor.txt in the same commit, so the")
                    appendLine("decision is in the diff and under review.")
                },
            )
        }

        if (pct > floor + 0.5) {
            println()
            println("Coverage ROSE to $rounded%. Raise the floor:")
            println("  echo $rounded > android/coverage-floor.txt")
            println("Not done automatically: a self-raising ratchet records")
            println("whatever the last run produced, including a run that")
            println("skipped tests.")
        }
    }
}

// Attached to `check`, so it runs on every PR rather than only when someone
// remembers. This is the whole difference between the toolchain existing and
// the toolchain being a control.
tasks.matching { it.name == "check" }.configureEach {
    dependsOn("verifyCoverageRatchet")
}
