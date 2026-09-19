plugins { id("com.android.application") }

android {
    namespace = "com.omega.app"
    compileSdk = 36
    defaultConfig {
        applicationId = "com.omega.app"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "1.0.0"
    }
    buildTypes {
        release { isMinifyEnabled = false }
    }
}
