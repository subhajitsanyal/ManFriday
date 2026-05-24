package com.manfriday.android

import android.content.Intent
import android.graphics.BitmapFactory
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import java.time.Duration
import java.time.Instant
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            ManFridayApp()
        }
    }
}

@Composable
fun ManFridayApp() {
    val context = LocalContext.current
    var backendUrl by rememberSaveable { mutableStateOf("http://10.0.2.2:8000") }
    var localSecret by rememberSaveable { mutableStateOf("") }
    var session by remember { mutableStateOf<SessionConnection?>(null) }
    var setupStatus by rememberSaveable { mutableStateOf("Ready") }
    var liveKitStatus by rememberSaveable { mutableStateOf("Disconnected") }
    var webSocketStatus by rememberSaveable { mutableStateOf("Disconnected") }
    var lastEvent by rememberSaveable { mutableStateOf("None") }
    var frameStatus by rememberSaveable { mutableStateOf("No frame") }
    var assistantStatus by rememberSaveable { mutableStateOf("Idle") }
    var transcriptEntries by remember { mutableStateOf<List<TranscriptEntry>>(emptyList()) }
    var latestFrameBitmap by remember { mutableStateOf<ImageBitmap?>(null) }
    var isFrameLoading by rememberSaveable { mutableStateOf(false) }
    var isLoading by rememberSaveable { mutableStateOf(false) }
    val audioClient = remember { LiveKitAudioClient(context) }
    var eventClient by remember { mutableStateOf<ManFridayWebSocketClient?>(null) }
    val scope = rememberCoroutineScope()
    val mainHandler = remember { Handler(Looper.getMainLooper()) }
    var androidTtsReady by remember { mutableStateOf(false) }
    val androidTts = remember {
        TextToSpeech(context) { status ->
            androidTtsReady = status == TextToSpeech.SUCCESS
        }
    }
    DisposableEffect(androidTts) {
        onDispose {
            androidTts.stop()
            androidTts.shutdown()
        }
    }
    val speakAssistant: (String, String) -> Unit = { turnId, text ->
        if (androidTtsReady && text.isNotBlank()) {
            androidTts.speak(text, TextToSpeech.QUEUE_FLUSH, null, turnId.ifBlank { "assistant" })
        }
    }
    val microphonePermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (!granted) {
            liveKitStatus = "Microphone denied"
        }
    }

    ManFridayTheme {
        Surface(modifier = Modifier.fillMaxSize()) {
            val activeSession = session
            if (activeSession != null) {
                ActiveCopilotScreen(
                    backendUrl = backendUrl,
                    session = activeSession,
                    liveKitStatus = liveKitStatus,
                    webSocketStatus = webSocketStatus,
                    lastEvent = lastEvent,
                    frameStatus = frameStatus,
                    assistantStatus = assistantStatus,
                    transcriptEntries = transcriptEntries,
                    latestFrameBitmap = latestFrameBitmap,
                    isFrameLoading = isFrameLoading,
                    onPushToTalkStart = {
                        runCatching {
                            ManFridayBackendClient.pushToTalkStart(
                                backendUrl = backendUrl,
                                localSecret = localSecret,
                                sessionId = activeSession.sessionId,
                            )
                        }.onSuccess {
                            assistantStatus = "Listening"
                            lastEvent = "assistant.push_to_talk.started"
                        }.onFailure {
                            assistantStatus = it.message ?: "Start failed"
                            lastEvent = assistantStatus
                        }.isSuccess
                    },
                    onPushToTalkRelease = { userText, hasSpeech ->
                        runCatching {
                            ManFridayBackendClient.pushToTalkRelease(
                                backendUrl = backendUrl,
                                localSecret = localSecret,
                                sessionId = activeSession.sessionId,
                                userText = userText,
                                hasSpeech = hasSpeech,
                            )
                        }.onSuccess {
                            assistantStatus = it.status.replaceFirstChar { char -> char.uppercase() }
                            lastEvent = "assistant.push_to_talk.${it.status}"
                        }.onFailure {
                            assistantStatus = it.message ?: "Release failed"
                            lastEvent = assistantStatus
                        }
                    },
                    onRefreshFrame = {
                        scope.launch {
                            isFrameLoading = true
                            frameStatus = "Loading latest frame"
                            runCatching {
                                val frame = ManFridayBackendClient.latestFrame(
                                    backendUrl = backendUrl,
                                    localSecret = localSecret,
                                    sessionId = activeSession.sessionId,
                                )
                                val bitmap = frame.jpegUrl?.let { jpegUrl ->
                                    ManFridayBackendClient.frameJpeg(
                                        backendUrl = backendUrl,
                                        localSecret = localSecret,
                                        jpegUrl = jpegUrl,
                                    )
                                }
                                frame to bitmap
                            }.onSuccess {
                                frameStatus = it.first.toStatusText()
                                latestFrameBitmap = it.second
                            }.onFailure {
                                frameStatus = it.message ?: "Latest frame failed"
                                latestFrameBitmap = null
                            }
                            isFrameLoading = false
                        }
                    },
                    onLook = {
                        scope.launch {
                            isFrameLoading = true
                            frameStatus = "Looking"
                            runCatching {
                                val frame = ManFridayBackendClient.lookFrame(
                                    backendUrl = backendUrl,
                                    localSecret = localSecret,
                                    sessionId = activeSession.sessionId,
                                )
                                val bitmap = frame.jpegUrl?.let { jpegUrl ->
                                    ManFridayBackendClient.frameJpeg(
                                        backendUrl = backendUrl,
                                        localSecret = localSecret,
                                        jpegUrl = jpegUrl,
                                    )
                                }
                                frame to bitmap
                            }.onSuccess {
                                frameStatus = it.first.toStatusText()
                                latestFrameBitmap = it.second
                                lastEvent = "frame.look"
                            }.onFailure {
                                frameStatus = it.message ?: "Look failed"
                                latestFrameBitmap = null
                            }
                            isFrameLoading = false
                        }
                    },
                    onReconnect = {
                        scope.launch {
                            isLoading = true
                            webSocketStatus = "Reconnecting"
                            runCatching {
                                val snapshot = ManFridayBackendClient.sessionStatus(
                                    backendUrl = backendUrl,
                                    localSecret = localSecret,
                                    sessionId = activeSession.sessionId,
                                )
                                eventClient?.close()
                                eventClient = startEventClient(
                                    backendUrl = backendUrl,
                                    localSecret = localSecret,
                                    sessionId = snapshot.sessionId,
                                    mainHandler = mainHandler,
                                    onStatus = { webSocketStatus = it },
                                    onEvent = { type, payload ->
                                        lastEvent = type
                                        handleAssistantEvent(
                                            type = type,
                                            payload = payload,
                                            onAssistantStatus = { assistantStatus = it },
                                            onTranscript = { entry ->
                                                transcriptEntries = transcriptEntries + entry
                                            },
                                            onSpeak = speakAssistant,
                                        )
                                    },
                                )
                                snapshot
                            }.onSuccess {
                                session = activeSession.copy(
                                    sessionId = it.sessionId,
                                    expiresAt = it.expiresAt,
                                    debugEnabled = it.debugEnabled,
                                )
                                lastEvent = "session.status.changed: ${it.status}"
                            }.onFailure {
                                webSocketStatus = "Reconnect failed"
                                lastEvent = it.message ?: "Reconnect failed"
                            }
                            isLoading = false
                        }
                    },
                    onEndSession = {
                        scope.launch {
                            isLoading = true
                            setupStatus = "Ending session"
                            liveKitStatus = "Disconnecting"
                            webSocketStatus = "Disconnecting"
                            runCatching {
                                eventClient?.close()
                                eventClient = null
                                audioClient.disconnect()
                                ManFridayBackendClient.endSession(
                                    backendUrl = backendUrl,
                                    localSecret = localSecret,
                                    sessionId = activeSession.sessionId,
                                )
                            }.onSuccess {
                                session = null
                                latestFrameBitmap = null
                                assistantStatus = "Idle"
                                transcriptEntries = emptyList()
                                setupStatus = "Session ended"
                                liveKitStatus = "Disconnected"
                                webSocketStatus = "Disconnected"
                                lastEvent = "session.ended"
                            }.onFailure {
                                setupStatus = it.message ?: "Failed to end session"
                                liveKitStatus = "Disconnect failed"
                                webSocketStatus = "Disconnect failed"
                            }
                            isLoading = false
                        }
                    },
                )
            } else {
                SetupScreen(
                    backendUrl = backendUrl,
                    localSecret = localSecret,
                    status = setupStatus,
                    isLoading = isLoading,
                    onBackendUrlChange = { backendUrl = it },
                    onLocalSecretChange = { localSecret = it },
                    onStartSession = {
                        scope.launch {
                            isLoading = true
                            setupStatus = "Starting session"
                            runCatching {
                                microphonePermissionLauncher.launch(android.Manifest.permission.RECORD_AUDIO)
                                val nextSession = ManFridayBackendClient.startSession(
                                    backendUrl = backendUrl,
                                    localSecret = localSecret,
                                )
                                liveKitStatus = "Connecting"
                                audioClient.connect(nextSession)
                                webSocketStatus = "Connecting"
                                eventClient?.close()
                                eventClient = startEventClient(
                                    backendUrl = backendUrl,
                                    localSecret = localSecret,
                                    sessionId = nextSession.sessionId,
                                    mainHandler = mainHandler,
                                    onStatus = { webSocketStatus = it },
                                    onEvent = { type, payload ->
                                        lastEvent = type
                                        handleAssistantEvent(
                                            type = type,
                                            payload = payload,
                                            onAssistantStatus = { assistantStatus = it },
                                            onTranscript = { entry ->
                                                transcriptEntries = transcriptEntries + entry
                                            },
                                            onSpeak = speakAssistant,
                                        )
                                    },
                                )
                                nextSession
                            }.onSuccess {
                                session = it
                                setupStatus = "Session active"
                                liveKitStatus = "Connected"
                                isFrameLoading = true
                                frameStatus = "Loading latest frame"
                                runCatching {
                                    val frame = ManFridayBackendClient.latestFrame(
                                        backendUrl = backendUrl,
                                        localSecret = localSecret,
                                        sessionId = it.sessionId,
                                    )
                                    val bitmap = frame.jpegUrl?.let { jpegUrl ->
                                        ManFridayBackendClient.frameJpeg(
                                            backendUrl = backendUrl,
                                            localSecret = localSecret,
                                            jpegUrl = jpegUrl,
                                        )
                                    }
                                    frame to bitmap
                                }.onSuccess { frame ->
                                    frameStatus = frame.first.toStatusText()
                                    latestFrameBitmap = frame.second
                                }.onFailure {
                                    frameStatus = "No frame"
                                    latestFrameBitmap = null
                                }
                                isFrameLoading = false
                            }.onFailure {
                                setupStatus = it.message ?: "Failed to start session"
                                liveKitStatus = "Disconnected"
                                webSocketStatus = "Disconnected"
                            }
                            isLoading = false
                        }
                    },
                )
            }
        }
    }
}

@Composable
private fun SetupScreen(
    backendUrl: String,
    localSecret: String,
    status: String,
    isLoading: Boolean,
    onBackendUrlChange: (String) -> Unit,
    onLocalSecretChange: (String) -> Unit,
    onStartSession: () -> Unit,
) {
    Scaffold { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("Man Friday", style = MaterialTheme.typography.headlineMedium)
            Text("Setup", style = MaterialTheme.typography.titleMedium)
            OutlinedTextField(
                modifier = Modifier.fillMaxWidth(),
                value = backendUrl,
                onValueChange = onBackendUrlChange,
                label = { Text("Backend URL") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
            )
            OutlinedTextField(
                modifier = Modifier.fillMaxWidth(),
                value = localSecret,
                onValueChange = onLocalSecretChange,
                label = { Text("Local secret") },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
            )
            StatusLine(label = "Backend", value = status)
            Button(
                modifier = Modifier.fillMaxWidth(),
                enabled = !isLoading && backendUrl.isNotBlank() && localSecret.isNotBlank(),
                onClick = onStartSession,
            ) {
                Text(if (isLoading) "Starting" else "Start session")
            }
        }
    }
}

@Composable
private fun ActiveCopilotScreen(
    backendUrl: String,
    session: SessionConnection,
    liveKitStatus: String,
    webSocketStatus: String,
    lastEvent: String,
    frameStatus: String,
    assistantStatus: String,
    transcriptEntries: List<TranscriptEntry>,
    latestFrameBitmap: ImageBitmap?,
    isFrameLoading: Boolean,
    onPushToTalkStart: suspend () -> Boolean,
    onPushToTalkRelease: suspend (String?, Boolean) -> Unit,
    onRefreshFrame: () -> Unit,
    onLook: () -> Unit,
    onReconnect: () -> Unit,
    onEndSession: () -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val releaseCallback by rememberUpdatedState(onPushToTalkRelease)
    var releaseSent by remember { mutableStateOf(false) }
    val speechRecognizer = remember {
        if (SpeechRecognizer.isRecognitionAvailable(context)) {
            SpeechRecognizer.createSpeechRecognizer(context)
        } else {
            null
        }
    }
    val speechIntent = remember {
        Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            .putExtra(
                RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                RecognizerIntent.LANGUAGE_MODEL_FREE_FORM,
            )
            .putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
    }
    DisposableEffect(speechRecognizer) {
        if (speechRecognizer != null) {
            speechRecognizer.setRecognitionListener(
                object : RecognitionListener {
                    override fun onReadyForSpeech(params: Bundle?) = Unit
                    override fun onBeginningOfSpeech() = Unit
                    override fun onRmsChanged(rmsdB: Float) = Unit
                    override fun onBufferReceived(buffer: ByteArray?) = Unit
                    override fun onEndOfSpeech() = Unit
                    override fun onPartialResults(partialResults: Bundle?) = Unit
                    override fun onEvent(eventType: Int, params: Bundle?) = Unit

                    override fun onResults(results: Bundle?) {
                        if (releaseSent) return
                        releaseSent = true
                        val text = results
                            ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                            ?.firstOrNull()
                            ?.trim()
                            .orEmpty()
                        scope.launch {
                            releaseCallback(text.takeIf { it.isNotBlank() }, text.isNotBlank())
                        }
                    }

                    override fun onError(error: Int) {
                        if (releaseSent) return
                        releaseSent = true
                        scope.launch {
                            releaseCallback(null, false)
                        }
                    }
                },
            )
        }
        onDispose {
            speechRecognizer?.destroy()
        }
    }

    Scaffold { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Column {
                    Text("Active Copilot", style = MaterialTheme.typography.titleLarge)
                    Text(backendUrl, style = MaterialTheme.typography.bodySmall)
                }
                TextButton(onClick = onEndSession) {
                    Text("End")
                }
            }

            StatusLine(label = "Backend", value = "Connected")
            StatusLine(label = "Session", value = session.sessionId)
            StatusLine(label = "LiveKit", value = "$liveKitStatus: ${session.livekitRoom}")
            StatusLine(label = "Events", value = webSocketStatus)
            StatusLine(label = "Last event", value = lastEvent)
            StatusLine(label = "Assistant", value = assistantStatus)
            StatusLine(label = "GoPro", value = "Pending")
            StatusLine(label = "Visual", value = frameStatus)

            latestFrameBitmap?.let { bitmap ->
                Image(
                    bitmap = bitmap,
                    contentDescription = "Latest frame",
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(220.dp)
                        .background(Color.Black),
                    contentScale = ContentScale.Fit,
                )
            }

            Spacer(modifier = Modifier.height(12.dp))

            Button(
                modifier = Modifier
                    .fillMaxWidth()
                    .pointerInput(session.sessionId) {
                        detectTapGestures(
                            onPress = {
                                val started = onPushToTalkStart()
                                if (started) {
                                    releaseSent = false
                                    if (speechRecognizer == null) {
                                        releaseSent = true
                                        onPushToTalkRelease(null, false)
                                    } else {
                                        speechRecognizer.startListening(speechIntent)
                                        tryAwaitRelease()
                                        speechRecognizer.stopListening()
                                    }
                                }
                            },
                        )
                    },
                onClick = {},
            ) {
                Text(if (assistantStatus == "Listening") "Release to ask" else "Hold to talk")
            }

            Button(
                modifier = Modifier.fillMaxWidth(),
                enabled = !isFrameLoading,
                onClick = onLook,
            ) {
                Text(if (isFrameLoading) "Looking" else "Look")
            }

            Button(
                modifier = Modifier.fillMaxWidth(),
                enabled = !isFrameLoading,
                onClick = onRefreshFrame,
            ) {
                Text("Refresh latest frame")
            }

            Button(
                modifier = Modifier.fillMaxWidth(),
                onClick = onReconnect,
            ) {
                Text("Reconnect")
            }

            Text("Transcript", style = MaterialTheme.typography.titleMedium)
            if (transcriptEntries.isEmpty()) {
                Text("No turns yet.", style = MaterialTheme.typography.bodyMedium)
            } else {
                transcriptEntries.forEach { entry ->
                    TranscriptLine(entry)
                }
            }
        }
    }
}

@Composable
private fun TranscriptLine(entry: TranscriptEntry) {
    Column(
        modifier = Modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(entry.role.replaceFirstChar { it.uppercase() }, style = MaterialTheme.typography.labelLarge)
        Text(entry.text, style = MaterialTheme.typography.bodyMedium)
        val frame = entry.frameId
        if (!frame.isNullOrBlank()) {
            Text("Frame $frame", style = MaterialTheme.typography.bodySmall)
        } else if (entry.visualContext == "unavailable" || entry.visualStatus == "degraded") {
            Text("Visual context unavailable", style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun StatusLine(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(label, style = MaterialTheme.typography.bodyMedium)
        Text(value, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun ManFridayTheme(content: @Composable () -> Unit) {
    MaterialTheme(content = content)
}

@Preview(showBackground = true)
@Composable
private fun SetupPreview() {
    ManFridayTheme {
        SetupScreen(
            backendUrl = "http://10.0.2.2:8000",
            localSecret = "secret",
            status = "Ready",
            isLoading = false,
            onBackendUrlChange = {},
            onLocalSecretChange = {},
            onStartSession = {},
        )
    }
}

data class SessionConnection(
    val sessionId: String,
    val livekitUrl: String,
    val livekitRoom: String,
    val livekitToken: String,
    val expiresAt: String,
    val debugEnabled: Boolean,
)

private data class SessionSnapshot(
    val sessionId: String,
    val status: String,
    val expiresAt: String,
    val debugEnabled: Boolean,
)

private data class PushToTalkStartResponse(
    val turnId: String,
    val status: String,
)

private data class PushToTalkReleaseResponse(
    val turnId: String,
    val status: String,
    val assistantText: String?,
)

private data class TranscriptEntry(
    val turnId: String,
    val role: String,
    val text: String,
    val frameId: String?,
    val visualContext: String?,
    val visualStatus: String?,
)

private data class FrameMetadata(
    val frameId: String?,
    val capturedAt: Instant?,
    val width: Int?,
    val height: Int?,
    val source: String?,
    val mimeType: String?,
    val jpegUrl: String?,
) {
    fun toStatusText(now: Instant = Instant.now()): String {
        val parts = mutableListOf<String>()
        frameId?.takeIf { it.isNotBlank() }?.let { parts += it }
        if (width != null && height != null) {
            parts += "${width}x$height"
        }
        capturedAt?.let { parts += "${Duration.between(it, now).toHumanAge()} old" }
        source?.takeIf { it.isNotBlank() }?.let { parts += it }
        mimeType?.takeIf { it.isNotBlank() }?.let { parts += it }
        jpegUrl?.takeIf { it.isNotBlank() }?.let { parts += "JPEG ready" }
        return parts.takeIf { it.isNotEmpty() }?.joinToString(" | ") ?: "Frame metadata received"
    }
}

private object ManFridayBackendClient {
    suspend fun startSession(
        backendUrl: String,
        localSecret: String,
    ): SessionConnection = withContext(Dispatchers.IO) {
        val response = request(
            method = "POST",
            url = "${backendUrl.trimEnd('/')}/session/start",
            localSecret = localSecret,
            body = "{}",
        )
        val json = JSONObject(response)
        val livekit = json.getJSONObject("livekit")
        SessionConnection(
            sessionId = json.getString("session_id"),
            livekitUrl = livekit.getString("url"),
            livekitRoom = livekit.getString("room"),
            livekitToken = livekit.getString("token"),
            expiresAt = json.getString("expires_at"),
            debugEnabled = json.getBoolean("debug_enabled"),
        )
    }

    suspend fun endSession(
        backendUrl: String,
        localSecret: String,
        sessionId: String,
    ) {
        withContext(Dispatchers.IO) {
            request(
                method = "POST",
                url = "${backendUrl.trimEnd('/')}/session/end",
                localSecret = localSecret,
                body = JSONObject().put("session_id", sessionId).toString(),
            )
        }
    }

    suspend fun sessionStatus(
        backendUrl: String,
        localSecret: String,
        sessionId: String,
    ): SessionSnapshot = withContext(Dispatchers.IO) {
        val response = request(
            method = "GET",
            url = "${backendUrl.trimEnd('/')}/session/status?session_id=$sessionId",
            localSecret = localSecret,
            body = "",
        )
        val json = JSONObject(response)
        SessionSnapshot(
            sessionId = json.getString("session_id"),
            status = json.getString("status"),
            expiresAt = json.getString("expires_at"),
            debugEnabled = json.getBoolean("debug_enabled"),
        )
    }

    suspend fun pushToTalkStart(
        backendUrl: String,
        localSecret: String,
        sessionId: String,
    ): PushToTalkStartResponse = withContext(Dispatchers.IO) {
        val response = request(
            method = "POST",
            url = "${backendUrl.trimEnd('/')}/assistant/push-to-talk/start",
            localSecret = localSecret,
            body = JSONObject().put("session_id", sessionId).toString(),
        )
        val json = JSONObject(response)
        PushToTalkStartResponse(
            turnId = json.getString("turn_id"),
            status = json.getString("status"),
        )
    }

    suspend fun pushToTalkRelease(
        backendUrl: String,
        localSecret: String,
        sessionId: String,
        userText: String?,
        hasSpeech: Boolean,
    ): PushToTalkReleaseResponse = withContext(Dispatchers.IO) {
        val response = request(
            method = "POST",
            url = "${backendUrl.trimEnd('/')}/assistant/push-to-talk/release",
            localSecret = localSecret,
            body = JSONObject()
                .put("session_id", sessionId)
                .put("user_text", userText)
                .put("has_speech", hasSpeech)
                .toString(),
        )
        val json = JSONObject(response)
        PushToTalkReleaseResponse(
            turnId = json.getString("turn_id"),
            status = json.getString("status"),
            assistantText = json.optNullableString("assistant_text"),
        )
    }

    suspend fun latestFrame(
        backendUrl: String,
        localSecret: String,
        sessionId: String,
    ): FrameMetadata = withContext(Dispatchers.IO) {
        val response = request(
            method = "GET",
            url = "${backendUrl.trimEnd('/')}/frame/latest?session_id=${sessionId.urlEncoded()}",
            localSecret = localSecret,
            body = "",
        )
        parseFrameMetadata(response)
    }

    suspend fun lookFrame(
        backendUrl: String,
        localSecret: String,
        sessionId: String,
    ): FrameMetadata = withContext(Dispatchers.IO) {
        val response = request(
            method = "POST",
            url = "${backendUrl.trimEnd('/')}/frame/look",
            localSecret = localSecret,
            body = JSONObject().put("session_id", sessionId).toString(),
        )
        parseFrameMetadata(response)
    }

    suspend fun frameJpeg(
        backendUrl: String,
        localSecret: String,
        jpegUrl: String,
    ): ImageBitmap = withContext(Dispatchers.IO) {
        val resolvedUrl = resolveBackendUrl(backendUrl, jpegUrl)
        val connection = (URL(resolvedUrl).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 5_000
            readTimeout = 10_000
            setRequestProperty("Authorization", "Bearer $localSecret")
            setRequestProperty("Accept", "image/jpeg")
        }
        try {
            val stream = if (connection.responseCode in 200..299) {
                connection.inputStream
            } else {
                connection.errorStream
            }
            val bytes = stream.use { it.readBytes() }
            if (connection.responseCode !in 200..299) {
                val errorText = bytes.toString(StandardCharsets.UTF_8)
                throw IllegalStateException("JPEG returned ${connection.responseCode}: $errorText")
            }
            val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                ?: throw IllegalStateException("JPEG response could not be decoded")
            bitmap.asImageBitmap()
        } finally {
            connection.disconnect()
        }
    }

    private fun request(
        method: String,
        url: String,
        localSecret: String,
        body: String,
    ): String {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 5_000
            readTimeout = 5_000
            doOutput = body.isNotEmpty()
            setRequestProperty("Authorization", "Bearer $localSecret")
            setRequestProperty("Content-Type", "application/json")
        }
        if (body.isNotEmpty()) {
            OutputStreamWriter(connection.outputStream).use { writer ->
                writer.write(body)
            }
        }
        val stream = if (connection.responseCode in 200..299) {
            connection.inputStream
        } else {
            connection.errorStream
        }
        val response = stream.bufferedReader().use { it.readText() }
        if (connection.responseCode !in 200..299) {
            throw IllegalStateException("Backend returned ${connection.responseCode}: $response")
        }
        return response
    }

    private fun parseFrameMetadata(response: String): FrameMetadata {
        val json = JSONObject(response)
        val frame = json.optJSONObject("frame") ?: json.optJSONObject("metadata") ?: json
        return FrameMetadata(
            frameId = frame.firstString("frame_id", "id", "name"),
            capturedAt = frame.firstInstant("captured_at", "timestamp", "created_at", "updated_at"),
            width = frame.firstInt("width", "image_width"),
            height = frame.firstInt("height", "image_height"),
            source = frame.firstString("source", "camera", "device"),
            mimeType = frame.firstString("mime_type", "content_type", "format"),
            jpegUrl = frame.firstString("jpeg_url", "jpg_url", "image_url", "url"),
        )
    }

    private fun resolveBackendUrl(backendUrl: String, pathOrUrl: String): String {
        val base = URL("${backendUrl.trimEnd('/')}/")
        return URL(base, pathOrUrl).toString()
    }
}

private fun JSONObject.firstString(vararg keys: String): String? {
    for (key in keys) {
        val value = optString(key, "")
        if (value.isNotBlank()) {
            return value
        }
    }
    return null
}

private fun JSONObject.firstInt(vararg keys: String): Int? {
    for (key in keys) {
        if (has(key) && !isNull(key)) {
            val value = optInt(key, -1)
            if (value >= 0) {
                return value
            }
        }
    }
    return null
}

private fun JSONObject.firstInstant(vararg keys: String): Instant? {
    for (key in keys) {
        if (has(key) && !isNull(key)) {
            val stringValue = optString(key, "")
            if (stringValue.isNotBlank()) {
                runCatching { return Instant.parse(stringValue) }
            }
            val epochSeconds = optLong(key, Long.MIN_VALUE)
            if (epochSeconds != Long.MIN_VALUE) {
                return if (epochSeconds > 10_000_000_000L) {
                    Instant.ofEpochMilli(epochSeconds)
                } else {
                    Instant.ofEpochSecond(epochSeconds)
                }
            }
        }
    }
    return null
}

private fun Duration.toHumanAge(): String {
    val seconds = seconds.coerceAtLeast(0)
    return when {
        seconds < 60 -> "${seconds}s"
        seconds < 3_600 -> "${seconds / 60}m"
        seconds < 86_400 -> "${seconds / 3_600}h"
        else -> "${seconds / 86_400}d"
    }
}

private fun String.urlEncoded(): String = URLEncoder.encode(this, StandardCharsets.UTF_8.name())

private fun startEventClient(
    backendUrl: String,
    localSecret: String,
    sessionId: String,
    mainHandler: Handler,
    onStatus: (String) -> Unit,
    onEvent: (String, JSONObject?) -> Unit,
): ManFridayWebSocketClient {
    val client = ManFridayWebSocketClient(
        backendUrl = backendUrl,
        sessionId = sessionId,
        bearerSecret = localSecret,
        callbacks = object : ManFridayWebSocketClient.Callbacks {
            override fun onTextMessage(message: String) {
                mainHandler.post {
                    val json = runCatching { JSONObject(message) }.getOrNull()
                    val type = json?.optString("type")?.takeIf { it.isNotBlank() } ?: "event"
                    val payload = json?.optJSONObject("payload")
                    val status = payload?.optString("status")
                    onStatus(if (status.isNullOrBlank()) "Connected" else "Connected: $status")
                    onEvent(type, payload)
                }
            }

            override fun onError(error: Throwable) {
                mainHandler.post {
                    onStatus("Error")
                    onEvent(error.message ?: "WebSocket error", null)
                }
            }

            override fun onClosed(code: Int?, reason: String?) {
                mainHandler.post {
                    onStatus("Disconnected")
                    onEvent(reason ?: code?.toString() ?: "closed", null)
                }
            }
        },
    )
    client.connect()
    return client
}

private fun handleAssistantEvent(
    type: String,
    payload: JSONObject?,
    onAssistantStatus: (String) -> Unit,
    onTranscript: (TranscriptEntry) -> Unit,
    onSpeak: (String, String) -> Unit,
) {
    when (type) {
        "assistant.state.changed" -> {
            val state = payload?.optString("assistant_state").orEmpty()
            if (state.isNotBlank()) {
                onAssistantStatus(state.replaceFirstChar { it.uppercase() })
            }
        }
        "assistant.response.started" -> onAssistantStatus("Thinking")
        "assistant.response.completed" -> onAssistantStatus("Idle")
        "assistant.error" -> {
            val message = payload?.optString("message").orEmpty()
            onAssistantStatus(message.ifBlank { "Assistant error" })
        }
        "assistant.transcript.delta" -> {
            val text = payload?.optString("text").orEmpty()
            if (payload != null && text.isNotBlank()) {
                val role = payload.optString("role", "assistant")
                val turnId = payload.optString("turn_id")
                onTranscript(
                    TranscriptEntry(
                        turnId = turnId,
                        role = role,
                        text = text,
                        frameId = payload.optNullableString("frame_id"),
                        visualContext = payload.optNullableString("visual_context"),
                        visualStatus = payload.optNullableString("visual_status"),
                    ),
                )
                if (role == "assistant" && payload.optBoolean("is_final", false)) {
                    onSpeak(turnId, text)
                }
            }
        }
    }
}

private fun JSONObject.optNullableString(key: String): String? {
    if (!has(key) || isNull(key)) {
        return null
    }
    return optString(key).takeIf { it.isNotBlank() }
}
