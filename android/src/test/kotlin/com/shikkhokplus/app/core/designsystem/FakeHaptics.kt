package com.shikkhokplus.app.core.designsystem

/** Records each haptic by name, for tests that have no motor to feel. */
class FakeHaptics : Haptics {
    val felt = mutableListOf<String>()

    override fun confirm() {
        felt += "confirm"
    }

    override fun reject() {
        felt += "reject"
    }

    override fun tick() {
        felt += "tick"
    }
}
