package app.meetsaathi.core

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

/**
 * Realtime session stream. Resumes from the last processed sequence after any disconnect, drops duplicates
 * and out-of-order replays (events are idempotent by sequence), and ACKs what it processed (master 10).
 */
class RealtimeClient(private val api: ApiClient, private val scope: CoroutineScope, private val sessionId: String, startCursor: Long) {
    private val _events = MutableSharedFlow<EventEnvelope>(extraBufferCapacity = 256)
    val events: SharedFlow<EventEnvelope> = _events
    private val _connected = MutableStateFlow(false)
    val connected: StateFlow<Boolean> = _connected

    @Volatile var cursor: Long = startCursor
        private set
    private var socket: WebSocket? = null
    private var loop: Job? = null
    @Volatile private var closed = false

    fun start() {
        closed = false
        loop = scope.launch {
            var backoff = 1000L
            while (!closed) {
                // Reconnects must refresh expired credentials through the same serialized HTTP path.
                try { api.prepareRealtimeAuth() }
                catch (_: Exception) { delay(backoff); backoff = (backoff * 2).coerceAtMost(30_000); continue }
                val done = kotlinx.coroutines.CompletableDeferred<Unit>()
                connect { done.complete(Unit) }
                done.await()
                _connected.value = false
                if (closed) break
                delay(backoff)
                backoff = (backoff * 2).coerceAtMost(30_000)
            }
        }
    }

    private fun connect(onClosed: () -> Unit) {
        val wsUrl = api.baseUrl.replaceFirst("http", "ws").trimEnd('/') + "/v1/sessions/$sessionId/realtime"
        socket = api.http.newWebSocket(Request.Builder().url(wsUrl).build(), object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                // Token travels in-band, never in the URL (privacy rule: no sensitive data in query strings).
                val auth = buildJsonObject {
                    put("type", "auth"); put("access_token", api.accessTokenForRealtime() ?: ""); put("cursor", cursor)
                }
                webSocket.send(auth.toString())
                _connected.value = true
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                val ev = runCatching { WireJson.decodeFromString(EventEnvelope.serializer(), text) }.getOrNull() ?: return
                when (ev.type) {
                    "ping" -> return
                    "error" -> { webSocket.close(1000, null); return }
                }
                if (ev.sequence <= cursor) return // duplicate replay after reconnect
                cursor = ev.sequence
                _events.tryEmit(ev)
                webSocket.send(buildJsonObject { put("type", "ack"); put("sequence", ev.sequence) }.toString())
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) = onClosed()
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) = onClosed()
        })
    }

    fun signalUserSpeaking(speaking: Boolean) {
        socket?.send(buildJsonObject { put("type", "signal"); put("user_speaking", JsonPrimitive(speaking)) }.toString())
    }

    fun reportRouteLost() {
        socket?.send(buildJsonObject { put("type", "voice.route_lost") }.toString())
    }

    fun stop() {
        closed = true
        socket?.close(1000, null)
        loop?.cancel()
    }
}
