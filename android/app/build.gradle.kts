plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val configuredOwnerApiBaseUrl = providers.gradleProperty("qc2OwnerApiBaseUrl")
    .orElse(providers.environmentVariable("QC2_OWNER_API_BASE_URL"))
    .getOrElse("")
val configuredBuildIdentity = providers.gradleProperty("qc2BuildIdentity")
    .orElse(providers.environmentVariable("GITHUB_SHA"))
    .getOrElse("local")

fun buildConfigLiteral(value: String): String =
    "\"${value.replace("\\", "\\\\").replace("\"", "\\\"")}\""

android {
    namespace = "com.lamontlabs.qc2owner"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.lamontlabs.qc2owner"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "OWNER_API_BASE_URL", buildConfigLiteral(configuredOwnerApiBaseUrl))
        buildConfigField("String", "BUILD_IDENTITY", buildConfigLiteral(configuredBuildIdentity))
    }

    buildFeatures {
        buildConfig = true
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.activity:activity-compose:1.10.0")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    debugImplementation("androidx.compose.ui:ui-tooling")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
