package com.manfriday.android

import android.content.Context
import io.livekit.android.LiveKit
import io.livekit.android.room.Room

class LiveKitAudioClient(context: Context) {
    private val appContext = context.applicationContext
    private var room: Room? = null

    suspend fun connect(connection: SessionConnection) {
        disconnect()
        val nextRoom = LiveKit.create(appContext)
        nextRoom.connect(
            url = connection.livekitUrl,
            token = connection.livekitToken,
        )
        nextRoom.localParticipant.setMicrophoneEnabled(true)
        room = nextRoom
    }

    suspend fun disconnect() {
        room?.localParticipant?.setMicrophoneEnabled(false)
        room?.disconnect()
        room = null
    }
}
