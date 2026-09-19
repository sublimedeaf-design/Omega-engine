# OMEGA Android build

Requirements: JDK 17+, Android SDK platform 36, Android Build Tools, Gradle/Gradle wrapper.

Build debug APK from `android/` with `./gradlew assembleDebug` once the wrapper/SDK are available.
The APK is produced at `app/build/outputs/apk/debug/app-debug.apk` and is debug-signed by the Android toolchain.

The client deliberately displays only rows exported by `omega export-app`; unverified, UNKNOWN, and odds <1.90 rows are filtered before they reach the app.
