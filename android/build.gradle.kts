plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.compose.compiler)
    alias(libs.plugins.spotless)
    alias(libs.plugins.detekt)
}

// ---------------------------------------------------------------------------
// The Kotlin quality toolchain.
//
// **Why these run on every PR and the release gates do not.** The gates in
// release-gates.gradle.kts are the strongest checks this project has, and
// until now they were the ONLY Kotlin checks -- and they run on
// `bundleRelease`. A `TelephonyManager` call could therefore sit on `main`
// through every pull request and be found on the build that was about to
// ship. These attach to `check`, so a forbidden identifier or an unformatted
// file fails on the commit that introduces it.
//
// This is the per-commit half of the rule affirmed 2026-10-22: enforce the
// forbidden-identifier set at commit time AS WELL AS at release time.
// ---------------------------------------------------------------------------

spotless {
    // **ktlint does NOT run over src/**/*.kt, and that is a decision rather
    // than an omission.** Decided 2026-10-22, after installing it and
    // finding it cannot parse this codebase.
    //
    // ktlint reads `[...]` inside a KDoc block as a Kotlin reference link,
    // so a traceability tag -- `/** Never read from the SIM [AC1.1.6]. */`
    // -- fails its parser with "closing bracket expected". The code
    // compiles; the formatter cannot read it. There are 52 such tags across
    // 21 of the 32 Kotlin files, and they are the convention that ties this
    // code to its requirements on both surfaces.
    //
    // Three options were weighed: escape every tag as a code span, move
    // tags out of KDoc into line comments, or drop the Kotlin formatter.
    // The first two change a convention used consistently across the
    // project to satisfy a tool's parser, which is the tail wagging the
    // dog -- and `team.md` is explicit that style is settled by a file in
    // the repository and that project constraints outrank the sample.
    //
    // **What covers Kotlin instead**: detekt for static analysis, Android
    // Lint with HardwareIds fatal, and the release DEX scan. Those catch
    // defects. Automated brace placement does not, and with one reviewer
    // the review is better spent on structure anyway [OC-6, D-45].
    //
    // The Gradle and XML targets below DO run: both parse cleanly, and
    // `strings.xml` carries the Bangla bundle, where a malformed entity or
    // a stray encoding is far easier to see in a consistently formatted
    // file.
    kotlinGradle {
        target("*.gradle.kts")
        ktlint(libs.versions.ktlint.get())
    }
    format("xml") {
        target("src/main/res/**/*.xml")
        trimTrailingWhitespace()
        endWithNewline()
    }
}

detekt {
    buildUponDefaultConfig = true
    config.setFrom(files("$rootDir/android/detekt.yml"))
    // The baseline is deliberately ABSENT. A baseline on a 32-file surface
    // would freeze today's findings as acceptable, and the whole reason this
    // toolchain arrives before D1 rather than after D6 is that the surface is
    // still small enough to fix rather than baseline.
    autoCorrect = false
}

android {
    // Permanent once published. [TC-2, D-38]
    namespace = "com.shikkhokplus.app"

    // API 36 (Android 16), rechecked at release. [TC-1, D-39]
    compileSdk = 36

    defaultConfig {
        applicationId = "com.shikkhokplus.app"
        minSdk = 24
        targetSdk = 36
        // **Supplied by the release pipeline**, defaulting to the
        // dev values. Play REJECTS an upload whose versionCode is not
        // strictly greater than every previous one, and that is not
        // reversible for that code -- so CI derives it from the run
        // number rather than leaving it to be remembered.
        versionCode = (project.findProperty("versionCode") as String?)
            ?.toInt() ?: 1
        versionName = (project.findProperty("versionName") as String?)
            ?: "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    // Package layout, not module layout: `core/*` and `feature/*` inside the
    // single module. See settings.gradle.kts.
    sourceSets {
        getByName("main") {
            kotlin.srcDirs("src/main/kotlin")
        }
        getByName("test") {
            kotlin.srcDirs("src/test/kotlin")
        }
    }

    signingConfigs {
        create("release") {
            // **Read from the environment, never from a file in the
            // repository** [project.md: NEVER hardcode a credential].
            // CI writes the keystore to a temp path from a base64
            // secret and removes it afterwards.
            //
            // All four absent means an UNSIGNED build, which is
            // correct for a local `assembleRelease` -- it must not
            // silently produce something that looks uploadable.
            val storePath = System.getenv("ANDROID_KEYSTORE_PATH")
            if (storePath != null) {
                storeFile = file(storePath)
                storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("ANDROID_KEY_ALIAS")
                keyPassword = System.getenv("ANDROID_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        debug {
            // The emulator reaches the host machine at 10.0.2.2. A
            // physical phone on the same wifi needs the machine's LAN
            // address instead -- override with
            // `-PapiBaseUrl=http://192.168.x.x:8000` or point it at
            // staging once TLS is up.
            buildConfigField(
                "String",
                "API_BASE_URL",
                "\"${project.findProperty("apiBaseUrl") ?: "http://10.0.2.2:8000"}\"",
            )
        }
        release {
            // No default. A release build must be told which backend it
            // talks to, because every possible default is wrong: a
            // developer's machine shipped to a phone, or a production
            // host reached from a test build.
            buildConfigField(
                "String",
                "API_BASE_URL",
                "\"${project.findProperty("apiBaseUrl") ?: ""}\"",
            )
            // **R8 is on, and the DEX gate is why.** It scans the
            // MINIFIED build: a debug build can differ in which
            // dependencies are present, and the release AAB is what
            // ships. Minifying also shrinks the bundle, but that is
            // the side effect rather than the reason.
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )

            // Only when the environment supplied a keystore. Without
            // it the build is unsigned and Play refuses it, which is
            // the correct failure -- better than a locally-signed
            // artifact that cannot be updated later.
            signingConfig = if (System.getenv("ANDROID_KEYSTORE_PATH") != null) {
                signingConfigs.getByName("release")
            } else {
                null
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    testOptions {
        unitTests {
            isReturnDefaultValues = true
            isIncludeAndroidResources = true
        }
    }

    // **Lint is configured by android/lint.xml**, where HardwareIds is
    // raised to fatal. The file carries the reasoning; what matters here is
    // that lint runs and that a fatal finding stops the build rather than
    // printing a warning nobody reads.
    lint {
        lintConfig = file("lint.xml")
        // An unchecked warning is a warning that accumulates. These two
        // turn the configured severities into a gate.
        abortOnError = true
        warningsAsErrors = false
        checkDependencies = true
        // A baseline is deliberately absent, for the same reason detekt has
        // none: the surface is 32 files and still small enough to fix.
        checkReleaseBuilds = true
        htmlReport = true
        xmlReport = true
    }
}

// **Dependency locking for this module's configurations.** The settings file
// locks the buildscript classpath; this locks what the app itself resolves.
// Both halves are needed: the version catalogue pins our DECLARED versions
// and says nothing about the transitive graph those declarations pull in.
dependencyLocking {
    lockAllConfigurations()
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

dependencies {
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.security.crypto)
    implementation(libs.ktor.client.core)
    implementation(libs.ktor.client.okhttp)
    implementation(libs.ktor.client.content.negotiation)
    implementation(libs.ktor.serialization.kotlinx.json)

    // Compose. The BOM pins every artifact from one version, so a
    // mismatched pair cannot arrive through a transitive bump.
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.activity.compose)
    implementation(libs.lifecycle.viewmodel.compose)
    // **Added when the third screen arrived, exactly as MainActivity
    // predicted it would be.** That file carried a note saying its
    // nullable-id navigation "is replaced the moment a third screen
    // needs a real back stack" — and 23 screens were built against 3
    // that could be reached, so signup existed and no one could open
    // it. The conventional Google choice, per the Android practice.
    implementation(libs.navigation.compose)

    testImplementation(libs.kotlin.test)
    testImplementation(libs.kotlin.test.junit)
    testImplementation(libs.coroutines.test)
    testImplementation(libs.ktor.client.mock)
    // Compose UI tests on the JVM: team.md names the OTP entry path as
    // an obligation, and a device-only test would run once at the
    // checkpoint rather than on every commit.
    testImplementation(platform(libs.compose.bom))
    testImplementation(libs.compose.ui.test.junit4)
    testImplementation(libs.robolectric)
    debugImplementation(libs.compose.ui.test.manifest)

    androidTestImplementation(platform(libs.compose.bom))
    androidTestImplementation(libs.compose.ui.test.junit4)
}

// **Robolectric's Android runtime arrives through Gradle, not mid-test.**
// Left alone, Robolectric downloads android-all-instrumented from Maven
// Central the first time a test needs it, outside Gradle: no retry, no
// build cache, no checksum verification. A dropped connection on the CI
// runner then failed whichever test happened to trigger the download, as
// a ConnectException that reads like a broken test. Resolving the jars as
// dependencies puts them under verification-metadata.xml and the Gradle
// cache, and offline mode makes a missing jar fail loudly instead of
// reaching for the network. Which jars, and why two, is recorded beside
// their versions in libs.versions.toml.
//
// One configuration per jar, because both are versions of the same module:
// in a single configuration Gradle's conflict resolution keeps the newer
// and silently drops the other.
val robolectricRuntimeSdk34: Configuration by configurations.creating {
    isTransitive = false
}
val robolectricRuntimeSdk35: Configuration by configurations.creating {
    isTransitive = false
}

dependencies {
    robolectricRuntimeSdk34(libs.robolectric.android.all.sdk34)
    robolectricRuntimeSdk35(libs.robolectric.android.all.sdk35)
}

val robolectricJarDir = layout.buildDirectory.dir("robolectric-jars")

val syncRobolectricJars by tasks.registering(Sync::class) {
    from(robolectricRuntimeSdk34, robolectricRuntimeSdk35)
    into(robolectricJarDir)
}

tasks.withType<Test>().configureEach {
    dependsOn(syncRobolectricJars)
    systemProperty("robolectric.offline", "true")
    systemProperty(
        "robolectric.dependency.dir",
        robolectricJarDir.get().asFile.absolutePath,
    )
}

// The two release-build gates team.md requires: the merged-manifest
// permission allowlist and the minified-DEX identifier scan.
apply(from = "release-gates.gradle.kts")

// The coverage ratchet. Separate file for the same reason the release gates
// are: each is a self-contained control with its own reasoning, and a build
// file that inlines all of them stops being readable.
apply(from = "coverage.gradle.kts")

// **Wired to the build, not left to be remembered.** A gate somebody
// has to invoke is a gate that gets skipped on the release that
// mattered.
//
// `tasks.matching` rather than `tasks.named` inside `afterEvaluate`:
// the AGP tasks are registered lazily, so naming them directly fails
// with "Task with name 'bundleRelease' not found" depending on when
// evaluation runs. Matching reacts whenever the task appears.
tasks.matching { it.name == "verifyReleasePermissions" }.configureEach {
    dependsOn("processReleaseManifest")
}
tasks.matching { it.name == "bundleRelease" }.configureEach {
    finalizedBy("verifyReleasePermissions", "verifyReleaseDex")
}

// **assembleRelease is gated too, and not because it is redundant.**
// The APK is built from the same `release` build type and therefore
// the same minified DEX, so in principle the AAB scan covers it. In
// principle is not the standard this file sets: `verifyReleaseDex`
// prefers the AAB when both exist, so without this line the published
// APK would ship having been scanned only by proxy. A gate that is
// satisfied by something it did not read is the failure its own guard
// exists to refuse.
tasks.matching { it.name == "assembleRelease" }.configureEach {
    finalizedBy("verifyReleasePermissions", "verifyReleaseDex")
}

// **The DEX gate must run AFTER the bundle is written, not merely
// after bundleRelease is requested.** `finalizedBy` alone let it open
// a stale or partial archive and report "no .dex entries" -- which
// its own guard caught, correctly refusing to pass on an empty scan.
tasks.matching { it.name == "verifyReleaseDex" }.configureEach {
    mustRunAfter("bundleRelease", "packageRelease")
}
