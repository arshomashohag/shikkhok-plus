plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.compose.compiler)
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
        versionCode = 1
        versionName = "0.1.0"
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
            // R8 and the release-build gates arrive with the packaging Bolt,
            // which is the first thing that needs them.
            isMinifyEnabled = false
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
