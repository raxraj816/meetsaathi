package app.meetsaathi.audio

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import app.meetsaathi.core.ApiClient
import app.meetsaathi.core.ApiException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Evidence player (U07/S14): plays exactly the permitted audio for one cited utterance, fetched from the server
 * span endpoint - never a neighbouring segment. The clip is written to the app cache only for playback and is
 * deleted as soon as playback stops, so no conversation audio lingers outside the encrypted spool.
 */
class EvidencePlayer(private val context: Context, private val api: ApiClient) {
    sealed interface State {
        data object Idle : State
        data class Loading(val utteranceId: String) : State
        data class Playing(val utteranceId: String) : State
        /** [code] is the API error code (AUDIO_DELETED, CLIP_UNAVAILABLE, OFFLINE, …); [message] is server copy if any. */
        data class Failed(val utteranceId: String, val code: String, val message: String) : State
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val _state = MutableStateFlow<State>(State.Idle)
    val state: StateFlow<State> = _state
    private var player: MediaPlayer? = null
    private var clip: File? = null
    private var job: Job? = null

    fun toggle(sessionId: String, utteranceId: String) {
        val cur = _state.value
        if ((cur is State.Playing && cur.utteranceId == utteranceId) || (cur is State.Loading && cur.utteranceId == utteranceId)) { stop(); return }
        play(sessionId, utteranceId)
    }

    fun play(sessionId: String, utteranceId: String) {
        stop()
        _state.value = State.Loading(utteranceId)
        job = scope.launch {
            try {
                val bytes = api.bytes("/v1/sessions/$sessionId/utterances/$utteranceId/audio")
                val f = withContext(Dispatchers.IO) {
                    File(context.cacheDir, "evidence").apply { mkdirs() }.let { d ->
                        File.createTempFile("clip", ".wav", d).apply { writeBytes(bytes) }
                    }
                }
                clip = f
                val mp = MediaPlayer().apply {
                    setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                    setDataSource(f.absolutePath)
                    setOnCompletionListener { stop() }
                    setOnErrorListener { _, _, _ -> fail(utteranceId, "PLAYBACK_FAILED", ""); true }
                    prepare()
                    start()
                }
                player = mp
                _state.value = State.Playing(utteranceId)
            } catch (e: ApiException) {
                fail(utteranceId, e.error.code, e.error.userMessage)
            } catch (e: app.meetsaathi.core.OfflineException) {
                fail(utteranceId, "OFFLINE", "")
            } catch (e: Exception) {
                fail(utteranceId, "PLAYBACK_FAILED", "")
            }
        }
    }

    private fun fail(utteranceId: String, code: String, message: String) {
        release()
        _state.value = State.Failed(utteranceId, code, message)
    }

    fun stop() {
        job?.cancel(); job = null
        release()
        _state.value = State.Idle
    }

    private fun release() {
        runCatching { player?.stop() }
        player?.release(); player = null
        clip?.delete(); clip = null
    }

    /** Remove any clip left behind by process death. */
    fun purgeCache() { File(context.cacheDir, "evidence").deleteRecursively() }
}
