#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ -x ./gradlew ]]; then ./gradlew clean assembleDebug
elif command -v gradle >/dev/null 2>&1; then gradle clean assembleDebug
else echo 'ERROR: Gradle/Gradle wrapper unavailable' >&2; exit 2
fi
APK=app/build/outputs/apk/debug/app-debug.apk
[[ -f "$APK" ]] || { echo 'ERROR: APK not produced' >&2; exit 3; }
echo "$APK"
