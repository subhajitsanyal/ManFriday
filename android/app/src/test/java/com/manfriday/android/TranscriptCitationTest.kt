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
}
