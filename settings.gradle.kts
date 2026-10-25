// One Gradle module for V1, not forty.
//
// `team.md` settles this deliberately: the reference sample uses roughly
// forty modules, and replicating that multiplies build configuration and
// build time for a two-surface solo project — a learning cost paid for
// nothing. The package structure inside `:android` is the sample's shape
// (`feature/*` plus `core/*`); converting packages to modules later is
// possible if it ever earns its keep.
//
// This is also why B1's Kotlin check is an SDK-using job rather than a plain
// JVM one: `core/model` lives inside an Android application module, so
// compiling it needs the Android Gradle Plugin. Splitting it out to avoid
// that would reopen a settled decision for the convenience of a CI step.

pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

// ---------------------------------------------------------------------------
// Dependency locking, added 2026-10-22.
//
// `team.md` named Gradle dependency locking plus `dependencyVerification`
// checksums as skeleton-time toolchain and neither landed, so until today the
// Kotlin surface resolved version RANGES on every build. The version
// catalogue pins what WE declare; it says nothing about what those
// dependencies pull in transitively, and the checksum file is the only
// control this project has that detects a tampered or substituted artifact in
// the Gradle supply chain.
//
// Locking is enabled here, at the settings level, so it applies to the
// buildscript classpath as well as the module's own configurations -- a
// compromised plugin is the more dangerous of the two and the one a
// module-level block would miss.
//
// Regenerate after a deliberate version change:
//   ./gradlew dependencies --write-locks
//   ./gradlew --write-verification-metadata sha256 help
// ---------------------------------------------------------------------------
buildscript {
    configurations.classpath {
        resolutionStrategy.activateDependencyLocking()
    }
}


rootProject.name = "shikkhokplus"

include(":android")
