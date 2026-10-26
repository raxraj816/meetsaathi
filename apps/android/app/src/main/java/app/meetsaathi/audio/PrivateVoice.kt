package app.meetsaathi.audio

import app.meetsaathi.R

import android.content.Context
import android.media.AudioAttributes
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import java.util.Locale
import java.util.UUID

/**
 * Private earbud voice (master 5.4, ADR-014). Checks the verified private route immediately before every
 * playback, stops instantly on route loss or barge-in, and NEVER falls back to the phone loudspeaker.
 */
class PrivateVoice(private val context: Context, private val routes: RouteMonitor, private val onPlayback: (startMs: Long, endMs: Long) -> Unit,
                   private val clockMs: () -> Long) {
    private var ready = false
    private var speakingStartedAt: Long? = null
    private val tts = TextToSpeech(context.applicationContext) { status -> ready = status == TextToSpeech.SUCCESS }

    init {
        tts.setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ASSISTANT)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
        tts.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) { speakingStartedAt = clockMs() }
            override fun onDone(utteranceId: String?) = finished()
            @Deprecated("Deprecated in Java") @Suppress("OVERRIDE_DEPRECATION") override fun onError(utteranceId: String?) = finished()
            override fun onStop(utteranceId: String?, interrupted: Boolean) = finished()
        })
        routes.onChange { _, new -> if (!new.privateOutputPresent || !routes.privateRouteVerified()) hardMute() }
    }

    private fun finished() {
        speakingStartedAt?.let { onPlayback(it, clockMs()) } // tell ASR this window was our own voice
        speakingStartedAt = null
    }

    val isSpeaking: Boolean get() = tts.isSpeaking

    /** Returns false (and says nothing) unless a verified private route exists right now. */
    fun speak(text: String, maxSeconds: Int = 7, locale: Locale = Locale.getDefault()): Boolean {
        if (!ready || !routes.privateRouteVerified()) return false
        val words = text.split(Regex("\\s+")).filter { it.isNotBlank() }
        val limited = words.take(maxSeconds * 5 / 2).joinToString(" ") // ~2.5 words/s keeps cues short
        tts.language = locale
        tts.speak(limited, TextToSpeech.QUEUE_FLUSH, Bundle(), UUID.randomUUID().toString())
        return true
    }

    /** Private route test sample: the only time audio plays before verification, and only to a private device. */
    fun playTestSample(deviceName: String?): Boolean {
        if (!ready || !routes.route.value.privateOutputPresent) return false
        val sample = if (deviceName != null) context.getString(R.string.voice_test_sample_named, deviceName) else context.getString(R.string.voice_test_sample)
        tts.speak(sample, TextToSpeech.QUEUE_FLUSH, Bundle(), "route-test")
        return true
    }

    fun hardMute() { if (tts.isSpeaking) tts.stop() }

    /** Barge-in: someone started talking - stop rather than talk over them (UNI-015). */
    fun onSpeechDetected() = hardMute()

    fun shutdown() { tts.stop(); tts.shutdown() }
}
