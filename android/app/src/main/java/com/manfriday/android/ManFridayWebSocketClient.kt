package com.manfriday.android

import java.io.BufferedInputStream
import java.io.ByteArrayOutputStream
import java.io.Closeable
import java.io.EOFException
import java.net.InetSocketAddress
import java.net.Socket
import java.net.URI
import java.net.URLEncoder
import java.nio.ByteBuffer
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Base64
import java.util.Locale
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import javax.net.ssl.SSLSocketFactory

class ManFridayWebSocketClient(
    private val backendUrl: String,
    private val sessionId: String,
    private val bearerSecret: String,
    private val callbacks: Callbacks,
) : Closeable {
    interface Callbacks {
        fun onTextMessage(message: String)
        fun onError(error: Throwable)
        fun onClosed(code: Int?, reason: String?)
    }

    private val executor: ExecutorService = Executors.newSingleThreadExecutor()
    private val random = SecureRandom()
    private val connected = AtomicBoolean(false)
    private val writeLock = Any()

    @Volatile
    private var socket: Socket? = null

    @Volatile
    private var input: BufferedInputStream? = null

    fun connect() {
        if (!connected.compareAndSet(false, true)) {
            return
        }

        executor.execute {
            runCatching {
                val uri = webSocketUri(backendUrl, sessionId)
                val activeSocket = openSocket(uri)
                val activeInput = BufferedInputStream(activeSocket.getInputStream())
                socket = activeSocket
                input = activeInput

                performHandshake(uri, activeSocket, activeInput)
                readLoop(activeInput)
            }.onFailure { error ->
                notifyError(error)
                closeSocket()
            }
        }
    }

    fun sendPing(payload: String = "") {
        val bytes = payload.toByteArray(StandardCharsets.UTF_8)
        require(bytes.size <= MAX_CONTROL_PAYLOAD_BYTES) {
            "WebSocket ping payload must be 125 bytes or less"
        }
        sendFrame(OPCODE_PING, bytes)
    }

    override fun close() {
        if (connected.get()) {
            runCatching { sendFrame(OPCODE_CLOSE, closePayload(NORMAL_CLOSE, "client closing")) }
        }
        closeSocket()
        executor.shutdownNow()
    }

    private fun openSocket(uri: URI): Socket {
        val secure = uri.scheme.equals("wss", ignoreCase = true)
        val port = effectivePort(uri)
        val rawSocket = if (secure) {
            SSLSocketFactory.getDefault().createSocket(uri.host, port) as Socket
        } else {
            Socket().apply {
                connect(InetSocketAddress(uri.host, port), CONNECT_TIMEOUT_MS)
            }
        }
        rawSocket.soTimeout = READ_TIMEOUT_MS
        return rawSocket
    }

    private fun performHandshake(
        uri: URI,
        activeSocket: Socket,
        activeInput: BufferedInputStream,
    ) {
        val keyBytes = ByteArray(16).also(random::nextBytes)
        val webSocketKey = Base64.getEncoder().encodeToString(keyBytes)
        val request = buildString {
            append("GET ${pathAndQuery(uri)} HTTP/1.1\r\n")
            append("Host: ${hostHeader(uri)}\r\n")
            append("Upgrade: websocket\r\n")
            append("Connection: Upgrade\r\n")
            append("Sec-WebSocket-Key: $webSocketKey\r\n")
            append("Sec-WebSocket-Version: 13\r\n")
            append("Authorization: Bearer $bearerSecret\r\n")
            append("\r\n")
        }

        activeSocket.getOutputStream().write(request.toByteArray(StandardCharsets.US_ASCII))
        activeSocket.getOutputStream().flush()

        val response = readHandshakeResponse(activeInput)
        val statusLine = response.firstOrNull().orEmpty()
        if (!statusLine.contains(" 101 ")) {
            throw IllegalStateException("WebSocket upgrade failed: $statusLine")
        }

        val headers = response.drop(1).mapNotNull { line ->
            val separator = line.indexOf(':')
            if (separator <= 0) {
                null
            } else {
                line.substring(0, separator).lowercase(Locale.US) to line.substring(separator + 1).trim()
            }
        }.toMap()
        val expectedAccept = webSocketAccept(webSocketKey)
        if (!headers["sec-websocket-accept"].equals(expectedAccept, ignoreCase = false)) {
            throw IllegalStateException("WebSocket upgrade returned an invalid accept key")
        }
    }

    private fun readLoop(activeInput: BufferedInputStream) {
        val fragments = ByteArrayOutputStream()
        var fragmentedOpcode: Int? = null

        while (connected.get()) {
            val frame = readFrame(activeInput)
            when (frame.opcode) {
                OPCODE_TEXT -> {
                    if (frame.fin) {
                        callbacks.onTextMessage(frame.payload.toString(StandardCharsets.UTF_8))
                    } else {
                        fragments.reset()
                        fragments.write(frame.payload)
                        fragmentedOpcode = OPCODE_TEXT
                    }
                }
                OPCODE_CONTINUATION -> {
                    if (fragmentedOpcode == OPCODE_TEXT) {
                        fragments.write(frame.payload)
                        if (frame.fin) {
                            callbacks.onTextMessage(fragments.toByteArray().toString(StandardCharsets.UTF_8))
                            fragments.reset()
                            fragmentedOpcode = null
                        }
                    }
                }
                OPCODE_PING -> sendFrame(OPCODE_PONG, frame.payload)
                OPCODE_CLOSE -> {
                    val closeInfo = parseClose(frame.payload)
                    runCatching { sendFrame(OPCODE_CLOSE, frame.payload) }
                    closeSocket(closeInfo.first, closeInfo.second)
                    return
                }
            }
        }
    }

    private fun readFrame(activeInput: BufferedInputStream): Frame {
        val first = activeInput.readRequiredByte()
        val second = activeInput.readRequiredByte()
        val fin = first and 0x80 != 0
        val opcode = first and 0x0f
        val masked = second and 0x80 != 0
        val baseLength = second and 0x7f
        val length = when (baseLength) {
            126 -> activeInput.readUnsignedShort()
            127 -> activeInput.readUnsignedLongLength()
            else -> baseLength.toLong()
        }
        require(length <= MAX_FRAME_BYTES) {
            "WebSocket frame is too large: $length bytes"
        }

        val mask = if (masked) ByteArray(4).also { readExact(activeInput, it) } else null
        val payload = ByteArray(length.toInt()).also { readExact(activeInput, it) }
        if (mask != null) {
            payload.indices.forEach { index ->
                payload[index] = (payload[index].toInt() xor mask[index % 4].toInt()).toByte()
            }
        }
        return Frame(fin = fin, opcode = opcode, payload = payload)
    }

    private fun sendFrame(opcode: Int, payload: ByteArray) {
        val activeSocket = socket ?: throw IllegalStateException("WebSocket is not connected")
        val frame = ByteArrayOutputStream()
        frame.write(0x80 or opcode)
        when {
            payload.size <= 125 -> frame.write(0x80 or payload.size)
            payload.size <= 65_535 -> {
                frame.write(0x80 or 126)
                frame.write((payload.size ushr 8) and 0xff)
                frame.write(payload.size and 0xff)
            }
            else -> {
                frame.write(0x80 or 127)
                frame.write(ByteBuffer.allocate(Long.SIZE_BYTES).putLong(payload.size.toLong()).array())
            }
        }

        val mask = ByteArray(4).also(random::nextBytes)
        frame.write(mask)
        payload.indices.forEach { index ->
            frame.write(payload[index].toInt() xor mask[index % 4].toInt())
        }

        synchronized(writeLock) {
            activeSocket.getOutputStream().write(frame.toByteArray())
            activeSocket.getOutputStream().flush()
        }
    }

    private fun closeSocket(code: Int? = null, reason: String? = null) {
        val wasConnected = connected.getAndSet(false)
        runCatching { socket?.close() }
        socket = null
        input = null
        if (wasConnected) {
            notifyClosed(code, reason)
        }
    }

    private fun notifyError(error: Throwable) {
        if (connected.get()) {
            callbacks.onError(error)
        }
    }

    private fun notifyClosed(code: Int?, reason: String?) {
        callbacks.onClosed(code, reason)
    }

    private data class Frame(
        val fin: Boolean,
        val opcode: Int,
        val payload: ByteArray,
    )

    companion object {
        private const val CONNECT_TIMEOUT_MS = 5_000
        private const val READ_TIMEOUT_MS = 0
        private const val MAX_CONTROL_PAYLOAD_BYTES = 125
        private const val MAX_FRAME_BYTES = 1_048_576L
        private const val NORMAL_CLOSE = 1000
        private const val OPCODE_CONTINUATION = 0x0
        private const val OPCODE_TEXT = 0x1
        private const val OPCODE_CLOSE = 0x8
        private const val OPCODE_PING = 0x9
        private const val OPCODE_PONG = 0xa
        private const val WEB_SOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

        private fun webSocketUri(backendUrl: String, sessionId: String): URI {
            val base = URI(backendUrl.trimEnd('/'))
            val scheme = when (base.scheme.lowercase(Locale.US)) {
                "http" -> "ws"
                "https" -> "wss"
                "ws", "wss" -> base.scheme.lowercase(Locale.US)
                else -> throw IllegalArgumentException("Unsupported WebSocket backend scheme: ${base.scheme}")
            }
            val encodedSessionId = URLEncoder.encode(sessionId, StandardCharsets.UTF_8.name())
            return URI("$scheme://${base.rawAuthority}/ws?session_id=$encodedSessionId")
        }

        private fun effectivePort(uri: URI): Int = when {
            uri.port > 0 -> uri.port
            uri.scheme.equals("wss", ignoreCase = true) -> 443
            else -> 80
        }

        private fun pathAndQuery(uri: URI): String {
            val path = uri.rawPath.takeUnless { it.isNullOrBlank() } ?: "/"
            return if (uri.rawQuery.isNullOrBlank()) path else "$path?${uri.rawQuery}"
        }

        private fun hostHeader(uri: URI): String {
            val port = uri.port
            val defaultPort = uri.scheme.equals("wss", ignoreCase = true) && port == 443 ||
                uri.scheme.equals("ws", ignoreCase = true) && port == 80
            return if (port <= 0 || defaultPort) uri.host else "${uri.host}:$port"
        }

        private fun readHandshakeResponse(input: BufferedInputStream): List<String> {
            val bytes = ByteArrayOutputStream()
            var previous3 = -1
            var previous2 = -1
            var previous1 = -1
            while (true) {
                val current = input.readRequiredByte()
                bytes.write(current)
                if (previous3 == '\r'.code &&
                    previous2 == '\n'.code &&
                    previous1 == '\r'.code &&
                    current == '\n'.code
                ) {
                    break
                }
                previous3 = previous2
                previous2 = previous1
                previous1 = current
            }
            return bytes.toString(StandardCharsets.ISO_8859_1.name())
                .trimEnd()
                .split("\r\n")
        }

        private fun webSocketAccept(key: String): String {
            val digest = MessageDigest.getInstance("SHA-1")
                .digest((key + WEB_SOCKET_GUID).toByteArray(StandardCharsets.US_ASCII))
            return Base64.getEncoder().encodeToString(digest)
        }

        private fun closePayload(code: Int, reason: String): ByteArray {
            val reasonBytes = reason.toByteArray(StandardCharsets.UTF_8)
            return ByteBuffer.allocate(Short.SIZE_BYTES + reasonBytes.size)
                .putShort(code.toShort())
                .put(reasonBytes)
                .array()
        }

        private fun parseClose(payload: ByteArray): Pair<Int?, String?> {
            if (payload.size < Short.SIZE_BYTES) {
                return null to null
            }
            val code = ByteBuffer.wrap(payload.take(Short.SIZE_BYTES).toByteArray()).short.toInt() and 0xffff
            val reason = payload.drop(Short.SIZE_BYTES)
                .toByteArray()
                .takeIf { it.isNotEmpty() }
                ?.toString(StandardCharsets.UTF_8)
            return code to reason
        }

        private fun BufferedInputStream.readRequiredByte(): Int {
            val value = read()
            if (value == -1) {
                throw EOFException("WebSocket connection closed")
            }
            return value
        }

        private fun readExact(input: BufferedInputStream, target: ByteArray) {
            var offset = 0
            while (offset < target.size) {
                val read = input.read(target, offset, target.size - offset)
                if (read == -1) {
                    throw EOFException("WebSocket connection closed")
                }
                offset += read
            }
        }

        private fun BufferedInputStream.readUnsignedShort(): Long {
            val high = readRequiredByte()
            val low = readRequiredByte()
            return ((high shl 8) or low).toLong()
        }

        private fun BufferedInputStream.readUnsignedLongLength(): Long {
            val bytes = ByteArray(Long.SIZE_BYTES).also { readExact(this, it) }
            val value = ByteBuffer.wrap(bytes).long
            if (value < 0) {
                throw IllegalArgumentException("WebSocket frame length exceeds supported range")
            }
            return value
        }
    }
}
