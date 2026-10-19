# R8 rules.
#
# **Minification is ON for release**, and not for size: the DEX gate
# scans the MINIFIED build, because that is what ships and because a
# debug build can differ in which dependencies are present.

# kotlinx.serialization generates serializers reflectively looked up by
# name. Without these, @Serializable classes fail to decode at RUNTIME
# with a confusing "Serializer for class X not found" -- and only in
# release, which is the worst place to find it.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
-keepclassmembers class kotlinx.serialization.json.** {
    *** Companion;
}
-keepclasseswithmembers class kotlinx.serialization.json.** {
    kotlinx.serialization.KSerializer serializer(...);
}
-keep,includedescriptorclasses class com.shikkhokplus.app.**$$serializer { *; }
-keepclassmembers class com.shikkhokplus.app.** {
    *** Companion;
}
-keepclasseswithmembers class com.shikkhokplus.app.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# Ktor's engine is selected via ServiceLoader.
-keep class io.ktor.client.engine.okhttp.** { *; }
-dontwarn org.slf4j.**
-dontwarn io.ktor.**

# **Money must not be stripped or renamed.** It is a @JvmInline value
# class whose serializer reads a JSON STRING and rejects a number
# [TC-7, D-20]. If R8 removed that serializer the decoder would fall
# back and the money boundary would be gone in release only.
-keep class com.shikkhokplus.app.core.model.Money { *; }
-keep class com.shikkhokplus.app.core.model.Money$* { *; }

# Keep line numbers so a release stack trace is readable. Costs a few
# KB; without it a crash report from closed testing is unusable.
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile

# **Tink's build-time annotations, absent at runtime by design.**
# androidx.security:security-crypto pulls Tink, which references
# com.google.errorprone annotations that are not packaged. R8 reports
# them as missing classes and fails the build.
#
# `-dontwarn` rather than adding errorprone as a dependency: these are
# source-retention annotations with no runtime behaviour, so shipping
# them would add weight for nothing.
-dontwarn com.google.errorprone.annotations.**
-dontwarn javax.annotation.**
-dontwarn com.google.api.client.http.**
-dontwarn org.joda.time.**

# Tink itself reflects over key-manager classes by name.
-keep class com.google.crypto.tink.** { *; }
