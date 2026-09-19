# Upload to GitHub

Target repository: `sublimedeaf-design/Omega-engine`

1. Extract this ZIP locally.
2. Upload the extracted repository contents to the repository root (not the ZIP itself).
3. Commit to `main`.
4. Open the repository's **Actions** tab.
5. Select **Build OMEGA APK**. A push touching `android/**` or the workflow file also triggers it automatically.
6. After the workflow succeeds, open the run and download the **OMEGA-debug-apk** artifact.

The workflow first runs the Python test suite, then builds `android/app/build/outputs/apk/debug/app-debug.apk`.

Note: this debug APK is an installable engineering build. It is not a signed Play Store release, and successful compilation is not evidence of betting profitability.
