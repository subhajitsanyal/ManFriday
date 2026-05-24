package com.manfriday.android

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TranscriptCitationTest {
    @Test
    fun transcriptEventParsesCitationReferences() {
        val payload = JSONObject(
            """
            {
              "turn_id": "turn_1",
              "role": "assistant",
              "text": "Use the small hex key.",
              "is_final": true,
              "citations": [
                {
                  "citation_id": "cite_1",
                  "source_title": "notes",
                  "source_uri": "notes.txt",
                  "section": null
                }
              ]
            }
            """.trimIndent(),
        )
        val entries = mutableListOf<TranscriptEntry>()
        val spoken = mutableListOf<String>()

        handleAssistantEvent(
            type = "assistant.transcript.delta",
            payload = payload,
            onAssistantStatus = {},
            onTranscript = { entries += it },
            onSpeak = { _, text -> spoken += text },
        )

        assertEquals(1, entries.size)
        assertEquals("assistant", entries[0].role)
        assertEquals("notes", entries[0].citations[0].sourceTitle)
        assertEquals("notes.txt", entries[0].citations[0].sourceUri)
        assertEquals(null, entries[0].citations[0].section)
        assertEquals(listOf("Use the small hex key."), spoken)
    }

    @Test
    fun citationDisplayTitleIncludesSectionWhenAvailable() {
        val citation = CitationReference(
            citationId = "cite_1",
            sourceTitle = "Workbench Safety Manual",
            sourceUri = "workbench_manual.md",
            section = "Clamp Setup",
        )

        assertEquals("Workbench Safety Manual | Clamp Setup", citation.displayTitle())
    }

    @Test
    fun transcriptEventWithoutCitationsKeepsEmptyCitationList() {
        val entries = mutableListOf<TranscriptEntry>()

        handleAssistantEvent(
            type = "assistant.transcript.delta",
            payload = JSONObject(
                """
                {
                  "turn_id": "turn_1",
                  "role": "assistant",
                  "text": "No citation on this answer.",
                  "is_final": true
                }
                """.trimIndent(),
            ),
            onAssistantStatus = {},
            onTranscript = { entries += it },
            onSpeak = { _, _ -> },
        )

        assertTrue(entries.single().citations.isEmpty())
    }

    @Test
    fun transcriptEventParsesSafetyAndTimingMetadata() {
        val entries = mutableListOf<TranscriptEntry>()
        val statuses = mutableListOf<String>()

        handleAssistantEvent(
            type = "assistant.transcript.delta",
            payload = JSONObject(
                """
                {
                  "turn_id": "turn_1",
                  "role": "assistant",
                  "text": "I do not have enough trusted retrieval context.",
                  "is_final": true,
                  "safety_action": "replaced_low_confidence_tool_instruction",
                  "safety_category": "retrieval_low_confidence",
                  "timing_ms": {
                    "response_start": 42,
                    "retrieval": 3,
                    "total": 99
                  }
                }
                """.trimIndent(),
            ),
            onAssistantStatus = { statuses += it },
            onTranscript = { entries += it },
            onSpeak = { _, _ -> },
        )

        val entry = entries.single()
        assertEquals("replaced_low_confidence_tool_instruction", entry.safetyAction)
        assertEquals("retrieval_low_confidence", entry.safetyCategory)
        assertEquals(42, entry.timingMs["response_start"])
        assertEquals(3, entry.timingMs["retrieval"])
        assertEquals("response 42ms | total 99ms | retrieval 3ms", entry.timingSummary())
        assertEquals("Low confidence", entry.assistantState)
        assertEquals(listOf("Low confidence"), statuses)
    }

    @Test
    fun transcriptEventParsesSafetyConstrainedState() {
        val entries = mutableListOf<TranscriptEntry>()
        val statuses = mutableListOf<String>()

        handleAssistantEvent(
            type = "assistant.transcript.delta",
            payload = JSONObject(
                """
                {
                  "turn_id": "turn_2",
                  "role": "assistant",
                  "text": "I cannot help bypass safety controls.",
                  "is_final": true,
                  "safety_action": "pre_model_constrained",
                  "safety_category": "bypass_safety_controls"
                }
                """.trimIndent(),
            ),
            onAssistantStatus = { statuses += it },
            onTranscript = { entries += it },
            onSpeak = { _, _ -> },
        )

        assertEquals("Safety constrained", entries.single().assistantState)
        assertEquals(listOf("Safety constrained"), statuses)
    }

    @Test
    fun statusHelpersExposeRequiredUiStates() {
        assertEquals("Backend unavailable", backendUiState("Disconnected"))
        assertEquals("Backend unavailable", backendUiState("Backend unavailable"))
        assertEquals("Connected", backendUiState("Connected: active"))
        assertEquals("LiveKit unavailable", liveKitUiState("Unavailable: room failed"))
        assertEquals("GoPro unavailable", goproUiState("No frame"))
        assertEquals("Visual degraded", goproUiState("visual_status=degraded"))
        assertEquals("Visual unavailable", visualUiState("unavailable"))
        assertEquals("Visual degraded", visualUiState("degraded"))
    }
}
