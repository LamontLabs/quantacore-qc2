package com.lamontlabs.qc2owner

import android.os.Bundle
import android.util.Base64
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

private val ownerTabs = listOf("Today", "Predictions", "Validation", "Models", "System")
private val projectionViews = listOf(
    "today", "predictions", "validation", "models", "system", "positions", "alerts",
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                OwnerApp()
            }
        }
    }
}

@Composable
private fun OwnerApp() {
    val context = LocalContext.current
    val secureStore = remember { OwnerSecureStore(context.applicationContext) }
    val client = remember {
        OwnerApiClient(
            BuildConfig.OWNER_API_BASE_URL,
            BuildConfig.VERSION_NAME,
            BuildConfig.BUILD_IDENTITY,
        )
    }
    val clipboard = LocalClipboardManager.current
    val scope = rememberCoroutineScope()

    var selectedTab by remember { mutableStateOf(0) }
    var session by remember { mutableStateOf<OwnerSession?>(null) }
    var pages by remember { mutableStateOf<Map<String, CachedOwnerPage>>(emptyMap()) }
    var onlineViews by remember { mutableStateOf<Set<String>>(emptySet()) }
    var serverOnline by remember { mutableStateOf(false) }
    var identityStatus by remember { mutableStateOf<JSONObject?>(null) }
    var busy by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var actionMessage by remember { mutableStateOf<String?>(null) }
    var pairingCode by remember { mutableStateOf("") }
    var recoveryMaterial by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        val cached = withContext(Dispatchers.IO) {
            projectionViews.mapNotNull { view ->
                secureStore.readPage(view)?.let { view to it }
            }.toMap()
        }
        pages = cached
        session = withContext(Dispatchers.IO) { secureStore.readSession() }
    }

    suspend fun ensureSession(forceRefresh: Boolean = false): OwnerSession? {
        val current = withContext(Dispatchers.IO) { secureStore.readSession() }
            ?: return null
        val now = System.currentTimeMillis()
        if (!forceRefresh && current.accessExpiresAtMillis > now + 30_000) return current
        if (current.refreshExpiresAtMillis <= now) {
            withContext(Dispatchers.IO) { secureStore.clearSession() }
            session = null
            return null
        }
        return try {
            val refreshed = withContext(Dispatchers.IO) {
                val (next, _) = client.refreshSession(current.refreshToken)
                secureStore.saveSession(next)
                next
            }
            session = refreshed
            refreshed
        } catch (error: Exception) {
            if (error is OwnerApiException && error.httpStatus == 401) {
                withContext(Dispatchers.IO) { secureStore.clearSession() }
                session = null
            }
            throw error
        }
    }

    suspend fun fetchProjectionSet(current: OwnerSession): Map<String, Result<JSONObject>> =
        coroutineScope {
            projectionViews.map { view ->
                async(Dispatchers.IO) {
                    view to runCatching { client.readProjection(current.accessToken, view) }
                }
            }.awaitAll().toMap()
        }

    suspend fun refreshProjections() {
        if (busy) return
        busy = true
        errorMessage = null
        try {
            var current = ensureSession()
            if (current == null) {
                serverOnline = false
                return
            }
            var results = fetchProjectionSet(current)
            if (results.values.any {
                    val failure = it.exceptionOrNull()
                    failure is OwnerApiException && failure.httpStatus == 401
                }) {
                current = ensureSession(forceRefresh = true)
                if (current == null) {
                    onlineViews = emptySet()
                    serverOnline = false
                    return
                }
                results = fetchProjectionSet(current)
            }

            val successfulViews = mutableMapOf<String, CachedOwnerPage>()
            for ((view, result) in results) {
                val page = result.getOrNull() ?: continue
                val cached = CachedOwnerPage(page.toString(), System.currentTimeMillis())
                withContext(Dispatchers.IO) {
                    secureStore.savePage(view, cached.json, cached.cachedAtMillis)
                }
                successfulViews[view] = cached
            }
            if (successfulViews.isNotEmpty()) {
                pages = pages + successfulViews
            }
            onlineViews = successfulViews.keys
            serverOnline = successfulViews.isNotEmpty()
            val failures = results.values.mapNotNull { it.exceptionOrNull() }
            if (failures.isNotEmpty() && successfulViews.isEmpty()) {
                errorMessage = friendlyError(failures.first())
            }
            val activeSession = current
            identityStatus = if (serverOnline) {
                runCatching {
                    withContext(Dispatchers.IO) {
                        client.readIdentityStatus(activeSession.accessToken)
                    }
                }.getOrNull()
            } else null
        } catch (error: Exception) {
            serverOnline = false
            onlineViews = emptySet()
            errorMessage = friendlyError(error)
        } finally {
            busy = false
        }
    }

    LaunchedEffect(session?.accessToken) {
        if (session != null) refreshProjections()
    }

    fun executeCommand(kind: String, body: JSONObject, label: String, requiredView: String) {
        if (busy || !serverOnline || requiredView !in onlineViews) {
            actionMessage = "Connect and refresh the server projection before authorizing this action."
            return
        }
        scope.launch {
            busy = true
            actionMessage = null
            try {
                val active = ensureSession()
                    ?: throw OwnerApiException(401, "session_expired")
                val response = withContext(Dispatchers.IO) {
                    client.submitSignedCommand(active.accessToken, kind, body)
                }
                val state = response.optJSONObject("execution")?.optString("status") ?: "UNKNOWN"
                val detail = response.optJSONObject("execution")?.optString("error_code")
                    ?.takeIf(String::isNotBlank)
                actionMessage = when (state) {
                    "COMPLETED" -> "$label completed by the hosted authority."
                    "PENDING", "PROCESSING", "RETRYABLE" ->
                        "$label was accepted; hosted execution is $state. Refresh System to check again."
                    "REJECTED" -> "$label was rejected${detail?.let { ": $it" } ?: "."}"
                    else -> "$label received an unrecognized execution state ($state)."
                }
                busy = false
                refreshProjections()
            } catch (error: Exception) {
                actionMessage = "$label failed: ${friendlyError(error)}"
                busy = false
            }
        }
    }

    fun enrollOwnerDevice() {
        if (busy) return
        val supplied = pairingCode.trim()
        if (!supplied.matches(Regex("^[A-Za-z0-9_-]{43}$"))) {
            errorMessage = "Enter the 5-minute pairing code issued from the owner console."
            return
        }
        scope.launch {
            busy = true
            errorMessage = null
            pairingCode = ""
            try {
                val (newSession, recovery) = withContext(Dispatchers.IO) {
                    client.enrollWithPairingCode(supplied)
                }
                withContext(Dispatchers.IO) { secureStore.saveSession(newSession) }
                session = newSession
                recoveryMaterial = recovery
                serverOnline = true
                actionMessage = "This Android device is enrolled with the hosted owner identity."
            } catch (error: Exception) {
                errorMessage = "Enrollment failed: ${friendlyError(error)}"
            } finally {
                busy = false
            }
        }
    }

    Scaffold(
        bottomBar = {
            NavigationBar {
                ownerTabs.forEachIndexed { index, label ->
                    NavigationBarItem(
                        selected = selectedTab == index,
                        onClick = { selectedTab = index },
                        icon = { Text(label.take(1)) },
                        label = { Text(label) },
                        modifier = Modifier.semantics {
                            contentDescription = "$label owner projection"
                        },
                    )
                }
            }
        },
    ) { padding ->
        Surface(
            modifier = Modifier.fillMaxSize().padding(padding),
            color = MaterialTheme.colorScheme.background,
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 18.dp, vertical = 14.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Column {
                        Text("QuantraCore Owner", style = MaterialTheme.typography.headlineSmall)
                        Text(
                            if (serverOnline) "Connected to hosted runtime"
                            else "Offline • read-only cached state",
                            style = MaterialTheme.typography.bodyMedium,
                        )
                    }
                    if (busy) CircularProgressIndicator()
                    else TextButton(
                        onClick = { scope.launch { refreshProjections() } },
                        enabled = session != null,
                    ) { Text("Refresh") }
                }

                Text(
                    if (BuildConfig.OWNER_API_BASE_URL.isBlank()) {
                        "Owner API URL is not configured in this build."
                    } else {
                        BuildConfig.OWNER_API_BASE_URL
                    },
                    style = MaterialTheme.typography.labelSmall,
                )

                errorMessage?.let { MessageCard("Connection", it) }
                actionMessage?.let { MessageCard("Action status", it) }

                if (session == null) {
                    EnrollmentCard(
                        pairingCode = pairingCode,
                        onPairingCodeChange = { pairingCode = it },
                        onEnroll = ::enrollOwnerDevice,
                        busy = busy,
                    )
                } else {
                    ProjectionScreen(
                        tab = ownerTabs[selectedTab],
                        pages = pages,
                        onlineViews = onlineViews,
                        serverOnline = serverOnline,
                        currentSession = session,
                        identityStatus = identityStatus,
                        busy = busy,
                        onCommand = ::executeCommand,
                    )
                }
            }
        }
    }

    recoveryMaterial?.let { recovery ->
        AlertDialog(
            onDismissRequest = { recoveryMaterial = null },
            title = { Text("Save owner recovery material") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("This value is shown once. Store it outside this app in a secure place.")
                    Text(recovery, style = MaterialTheme.typography.bodySmall)
                    OutlinedButton(onClick = {
                        clipboard.setText(AnnotatedString(recovery))
                        actionMessage = "Recovery material copied. Clear the clipboard after saving it."
                    }) { Text("Copy once") }
                }
            },
            confirmButton = {
                TextButton(onClick = { recoveryMaterial = null }) { Text("Done") }
            },
        )
    }
}

@Composable
private fun EnrollmentCard(
    pairingCode: String,
    onPairingCodeChange: (String) -> Unit,
    onEnroll: () -> Unit,
    busy: Boolean,
) {
    Card {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text("Enroll this owner device", style = MaterialTheme.typography.titleLarge)
            Text(
                "Get a one-time pairing code from the Clerk-protected owner console. It expires in 5 minutes; this device signs the server challenge with its Android Keystore key.",
            )
            OutlinedTextField(
                value = pairingCode,
                onValueChange = onPairingCodeChange,
                modifier = Modifier.fillMaxWidth(),
                label = { Text("One-time pairing code") },
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Ascii),
                singleLine = true,
                enabled = !busy,
            )
            Button(
                onClick = onEnroll,
                enabled = !busy && BuildConfig.OWNER_API_BASE_URL.isNotBlank(),
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Enroll securely") }
            Text(
                "This app requires a deployed HTTPS Owner API. It never connects to PostgreSQL.",
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}

@Composable
private fun ProjectionScreen(
    tab: String,
    pages: Map<String, CachedOwnerPage>,
    onlineViews: Set<String>,
    serverOnline: Boolean,
    currentSession: OwnerSession?,
    identityStatus: JSONObject?,
    busy: Boolean,
    onCommand: (String, JSONObject, String, String) -> Unit,
) {
    val primaryView = tab.lowercase()
    val primary = pages[primaryView]
    if (primary == null) {
        Text("No cached $tab projection is available yet.")
        return
    }

    val primaryPage = runCatching { JSONObject(primary.json) }.getOrNull()
    Text(tab, style = MaterialTheme.typography.titleLarge)
    Text(
        if (primaryView in onlineViews) "Live server projection"
        else "Cached ${ageLabel(primary.cachedAtMillis)} • read-only",
        style = MaterialTheme.typography.labelMedium,
    )
    primaryPage?.let { ProjectionMetadata(it) }
    primaryPage?.let { page ->
        val items = page.optJSONArray("items") ?: JSONArray()
        items.forEachElement { item ->
            val itemObject = item as? JSONObject ?: return@forEachElement
            val payload = itemObject.optJSONObject("payload") ?: return@forEachElement
            ProjectionItem(payload)
            if (tab == "Models" &&
                payload.optString("schema_name") == "qc2.governance_owner.PromotionChallenge.v1" &&
                payload.optString("state") == "PENDING"
            ) {
                val requestId = payload.optString("promotion_request_id")
                val bundleHash = payload.optString("bundle_hash")
                val requestHash = payload.optString("request_hash")
                if (requestId.isNotBlank() && bundleHash.isNotBlank() && requestHash.isNotBlank()) {
                    Button(
                        enabled = serverOnline && "models" in onlineViews && !busy,
                        onClick = {
                            onCommand(
                                "promotion-decision",
                                OwnerCommandBuilder.approvePromotion(requestId, bundleHash, requestHash),
                                "Promotion approval",
                                "models",
                            )
                        },
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("Approve eligible promotion") }
                }
            }
            if (tab == "System" &&
                payload.optString("schema_name") == "qc2.owner_api.PaperExecutionControlProjection.v1"
            ) {
                PaperControlActions(payload, serverOnline, onlineViews, busy, onCommand)
            }
        }
    }

    if (tab == "Today") {
        RelatedProjection(
            "Prioritized attention",
            pages["alerts"],
            onlineViews,
            "alerts",
            serverOnline,
            busy,
            onCommand,
        )
        RelatedProjection(
            "Paper positions",
            pages["positions"],
            onlineViews,
            "positions",
            serverOnline,
            busy,
            onCommand,
        )
    }
    if (tab == "System") {
        DeviceManagement(identityStatus, currentSession, serverOnline, onlineViews, busy, onCommand)
    }
}

@Composable
private fun ProjectionMetadata(page: JSONObject) {
    val projectionSequence = page.optLong("projection_sequence", -1)
    val sourceSequence = page.optLong("source_sequence", -1)
    val stale = page.optBoolean("stale", false)
    val state = page.optString("data_state", "UNKNOWN")
    Text(
        "State: $state • ${if (stale) "stale" else "current"}",
        style = MaterialTheme.typography.bodyMedium,
    )
    Text(
        "Projection $projectionSequence • source $sourceSequence • built ${page.optString("built_at", "unknown")}",
        style = MaterialTheme.typography.bodySmall,
    )
}

@Composable
private fun RelatedProjection(
    heading: String,
    cached: CachedOwnerPage?,
    onlineViews: Set<String>,
    view: String,
    serverOnline: Boolean,
    busy: Boolean,
    onCommand: (String, JSONObject, String, String) -> Unit,
) {
    Text(heading, style = MaterialTheme.typography.titleMedium)
    if (cached == null) {
        Text("No $heading projection is available.")
        return
    }
    if (view !in onlineViews) Text("Cached ${ageLabel(cached.cachedAtMillis)} • read-only")
    val page = runCatching { JSONObject(cached.json) }.getOrNull()
    val items = page?.optJSONArray("items") ?: JSONArray()
    if (items.length() == 0) Text("No items reported by the server.")
    items.forEachElement { raw ->
        val item = raw as? JSONObject ?: return@forEachElement
        val payload = item.optJSONObject("payload") ?: return@forEachElement
        ProjectionItem(payload, compact = true)
        if (
            view == "alerts" &&
            payload.optString("schema_name") == "qc2.governance_owner.Alert.v1" &&
            !payload.optBoolean("acknowledged", false)
        ) {
            val alertId = item.optJSONObject("source_ref")?.optString("target_id").orEmpty()
            val sequence = page?.optLong("projection_sequence", 0L) ?: 0L
            if (alertId.isNotBlank() && sequence > 0) {
                OutlinedButton(
                    enabled = serverOnline && view in onlineViews && !busy,
                    onClick = {
                        onCommand(
                            "alert-acknowledgment",
                            OwnerCommandBuilder.acknowledgeAlert(alertId, sequence),
                            "Alert acknowledgement",
                            view,
                        )
                    },
                ) { Text("Acknowledge alert") }
            }
        }
    }
}

@Composable
private fun ProjectionItem(payload: JSONObject, compact: Boolean = false) {
    val schemaName = payload.optString("schema_name", "Server item")
    val title = schemaName.substringAfterLast(".").removeSuffix(".v1")
    Card {
        Column(
            modifier = Modifier.fillMaxWidth().padding(if (compact) 12.dp else 14.dp),
            verticalArrangement = Arrangement.spacedBy(5.dp),
        ) {
            Text(title, style = MaterialTheme.typography.titleSmall)
            payload.keys().asSequence().filter(::isSafeDisplayKey).forEach { key ->
                if (key == "schema_name" || key == "schema_version") return@forEach
                val value = payload.opt(key)
                Text(
                    "${key.replace('_', ' ')}: ${formatValue(value)}",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}

@Composable
private fun PaperControlActions(
    payload: JSONObject,
    serverOnline: Boolean,
    onlineViews: Set<String>,
    busy: Boolean,
    onCommand: (String, JSONObject, String, String) -> Unit,
) {
    val generation = payload.optLong("state_version", -1)
    val paused = payload.optBoolean("entries_paused", false)
    val emergencyHalted = payload.optBoolean("emergency_halted", false)
    if (emergencyHalted) {
        Text("Emergency halt is active. Resume is not offered by this owner control.")
    } else if (generation >= 0 && !paused) {
        Button(
            enabled = serverOnline && "system" in onlineViews && !busy,
            onClick = {
                onCommand(
                    "entry-pause",
                    OwnerCommandBuilder.pauseEntries(generation, "owner_request"),
                    "Paper-entry pause",
                    "system",
                )
            },
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Pause new paper entries") }
    } else if (generation > 0 && paused) {
        Button(
            enabled = serverOnline && "system" in onlineViews && !busy,
            onClick = {
                onCommand(
                    "resume-request",
                    OwnerCommandBuilder.requestResume(generation),
                    "Paper-entry resume request",
                    "system",
                )
            },
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Request resume of paper entries") }
    }
}

@Composable
private fun DeviceManagement(
    status: JSONObject?,
    currentSession: OwnerSession?,
    serverOnline: Boolean,
    onlineViews: Set<String>,
    busy: Boolean,
    onCommand: (String, JSONObject, String, String) -> Unit,
) {
    Text("Authorized devices", style = MaterialTheme.typography.titleMedium)
    val devices = status?.optJSONArray("enrolled_devices")
    if (status == null || "system" !in onlineViews) {
        Text("Device state is unavailable offline. Revocation controls require a fresh server response.")
        return
    }
    if (devices == null || devices.length() == 0) {
        Text("The server reports no enrolled devices.")
        return
    }
    devices.forEachElement { raw ->
        val device = raw as? JSONObject ?: return@forEachElement
        val id = device.optString("id", device.optString("device_id"))
        val state = device.optString("revocation_state", device.optString("state", "UNKNOWN"))
        val keyId = device.optString("owner_key_id", "Owner device")
        Card {
            Column(
                modifier = Modifier.fillMaxWidth().padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Text(keyId, style = MaterialTheme.typography.titleSmall)
                Text("State: $state", style = MaterialTheme.typography.bodySmall)
                if (id.isNotBlank() && id == currentSession?.deviceId) {
                    Text("This device", style = MaterialTheme.typography.labelMedium)
                } else if (
                    id.isNotBlank() &&
                    state == "ENROLLED" &&
                    currentSession?.deviceId != null
                ) {
                    OutlinedButton(
                        enabled = serverOnline && !busy,
                        onClick = {
                            onCommand(
                                "device-management",
                                OwnerCommandBuilder.revokeDevice(id),
                                "Device revocation",
                                "system",
                            )
                        },
                    ) { Text("Revoke this device") }
                }
            }
        }
    }
}

@Composable
private fun MessageCard(title: String, message: String) {
    Card {
        Column(
            modifier = Modifier.fillMaxWidth().padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(title, style = MaterialTheme.typography.titleSmall)
            Text(message, style = MaterialTheme.typography.bodySmall)
        }
    }
}

private fun isSafeDisplayKey(key: String): Boolean =
    !Regex("(?i)(token|secret|private|credential|password|signature|public_key|api_key)")
        .containsMatchIn(key)

private inline fun JSONArray.forEachElement(action: (Any?) -> Unit) {
    for (index in 0 until length()) action(opt(index))
}

private fun formatValue(value: Any?): String {
    val rendered = when (value) {
        null, JSONObject.NULL -> "—"
        is JSONObject, is JSONArray -> value.toString()
        else -> value.toString()
    }
    return if (rendered.length > 240) rendered.take(237) + "…" else rendered
}

private fun ageLabel(cachedAtMillis: Long): String {
    val elapsed = (System.currentTimeMillis() - cachedAtMillis).coerceAtLeast(0)
    val seconds = elapsed / 1000
    return when {
        seconds < 60 -> "${seconds}s ago"
        seconds < 3600 -> "${seconds / 60}m ago"
        else -> "${seconds / 3600}h ago"
    }
}

private fun friendlyError(error: Throwable): String = when (error) {
    is OwnerApiException -> when (error.httpStatus) {
        401 -> "Owner session expired or revoked. Reconnect while online."
        403 -> "The server did not authorize this device or action."
        404 -> "The requested server resource was not found."
        409 -> "The canonical server state changed; refresh before trying again."
        429 -> "Too many requests. Try again shortly."
        in 500..599 -> "The hosted Owner API is temporarily unavailable."
        else -> error.errorCode ?: "The hosted API rejected the request."
    }
    else -> when (error.message) {
        "owner_api_https_origin_required" -> "This build needs a valid HTTPS Owner API base URL."
        "bootstrap_secret_too_short" -> "The bootstrap secret is invalid."
        else -> "Could not reach the hosted Owner API. Cached projections remain read-only."
    }
}
