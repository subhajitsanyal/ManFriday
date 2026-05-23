package com.manfriday.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp

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
    var isSessionActive by rememberSaveable { mutableStateOf(false) }
    var backendUrl by rememberSaveable { mutableStateOf("http://10.0.2.2:8000") }
    var localSecret by rememberSaveable { mutableStateOf("") }

    ManFridayTheme {
        Surface(modifier = Modifier.fillMaxSize()) {
            if (isSessionActive) {
                ActiveCopilotScreen(
                    backendUrl = backendUrl,
                    onEndSession = { isSessionActive = false },
                )
            } else {
                SetupScreen(
                    backendUrl = backendUrl,
                    localSecret = localSecret,
                    onBackendUrlChange = { backendUrl = it },
                    onLocalSecretChange = { localSecret = it },
                    onStartSession = { isSessionActive = true },
                )
            }
        }
    }
}

@Composable
private fun SetupScreen(
    backendUrl: String,
    localSecret: String,
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
            Button(
                modifier = Modifier.fillMaxWidth(),
                enabled = backendUrl.isNotBlank() && localSecret.isNotBlank(),
                onClick = onStartSession,
            ) {
                Text("Start session")
            }
        }
    }
}

@Composable
private fun ActiveCopilotScreen(
    backendUrl: String,
    onEndSession: () -> Unit,
) {
    var isListening by remember { mutableStateOf(false) }

    Scaffold { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
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

            StatusLine(label = "Backend", value = "Configured")
            StatusLine(label = "LiveKit", value = "Pending")
            StatusLine(label = "GoPro", value = "Pending")
            StatusLine(label = "Visual", value = "No frame")

            Spacer(modifier = Modifier.height(12.dp))

            Button(
                modifier = Modifier.fillMaxWidth(),
                onClick = { isListening = !isListening },
            ) {
                Text(if (isListening) "Release to ask" else "Hold to talk")
            }

            Button(
                modifier = Modifier.fillMaxWidth(),
                onClick = {},
            ) {
                Text("Look")
            }

            Text("Transcript", style = MaterialTheme.typography.titleMedium)
            Text("No turns yet.", style = MaterialTheme.typography.bodyMedium)
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
            onBackendUrlChange = {},
            onLocalSecretChange = {},
            onStartSession = {},
        )
    }
}
