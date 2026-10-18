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

rootProject.name = "shikkhokplus"

include(":android")
