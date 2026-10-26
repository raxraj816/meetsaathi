package app.meetsaathi.audio

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioAttributes
import android.media.AudioDeviceCallback
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

data class AudioRoute(
    val input: String,               // phone_mic | headset_mic | bluetooth_mic | usb_mic | none
    val output: String,              // phone_speaker | bluetooth_a2dp | bluetooth_le | bluetooth_sco | wired_headphones | usb_headset | none
    val outputDeviceName: String?,
    val privateOutputPresent: Boolean,
    val couplesInputAndOutput: Boolean, // HFP/SCO headsets move the microphone to the headset too
)

/**
 * Observes the REAL input/output routes (never optimistic labels). "Private" output means headphones/earbuds
 * that are actually connected right now; the user's sample-playback confirmation upgrades it to "verified".
 */
class RouteMonitor(private val context: Context) {
    private val am = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private val _route = MutableStateFlow(compute())
    val route: StateFlow<AudioRoute> = _route
    private val listeners = mutableListOf<(old: AudioRoute, new: AudioRoute) -> Unit>()
    @Volatile var userVerifiedPrivate: Boolean = false
        private set
    private var verifiedDevice: String? = null

    private val callback = object : AudioDeviceCallback() {
        override fun onAudioDevicesAdded(addedDevices: Array<out AudioDeviceInfo>) = refresh()
        override fun onAudioDevicesRemoved(removedDevices: Array<out AudioDeviceInfo>) = refresh()
    }
    private val noisy = object : BroadcastReceiver() {
        override fun onReceive(c: Context, i: Intent) = refresh(forceLoss = true) // headphones unplugged / BT dropped
    }

    fun start() {
        am.registerAudioDeviceCallback(callback, Handler(Looper.getMainLooper()))
        context.registerReceiver(noisy, IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY))
        refresh()
    }

    fun stop() {
        am.unregisterAudioDeviceCallback(callback)
        runCatching { context.unregisterReceiver(noisy) }
    }

    fun onChange(l: (AudioRoute, AudioRoute) -> Unit) { listeners += l }

    /** User heard the private test sample through [deviceName]. Invalidated by any route change. */
    fun confirmPrivateRoute() {
        val r = _route.value
        if (r.privateOutputPresent) {
            userVerifiedPrivate = true
            verifiedDevice = r.outputDeviceName
        }
    }

    fun privateRouteVerified(): Boolean = userVerifiedPrivate && _route.value.privateOutputPresent &&
        _route.value.outputDeviceName == verifiedDevice

    fun refresh(forceLoss: Boolean = false) {
        val old = _route.value
        val new = compute()
        if (forceLoss || new.output != old.output || new.outputDeviceName != old.outputDeviceName || !new.privateOutputPresent) {
            if (forceLoss || new.outputDeviceName != verifiedDevice || !new.privateOutputPresent) {
                userVerifiedPrivate = false // ADR-014: resume requires a fresh route check
            }
        }
        _route.value = new
        if (old != new || forceLoss) listeners.forEach { it(old, new) }
    }

    private fun compute(): AudioRoute {
        val outputs = am.getDevices(AudioManager.GET_DEVICES_OUTPUTS)
        val inputs = am.getDevices(AudioManager.GET_DEVICES_INPUTS)
        val media = if (Build.VERSION.SDK_INT >= 33) {
            am.getAudioDevicesForAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ASSISTANT).build()).firstOrNull()
        } else {
            outputs.firstOrNull { it.type in PRIVATE_TYPES } ?: outputs.firstOrNull { it.type == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER }
        }
        val outType = media?.type
        val output = when (outType) {
            AudioDeviceInfo.TYPE_BLUETOOTH_A2DP -> "bluetooth_a2dp"
            AudioDeviceInfo.TYPE_BLUETOOTH_SCO -> "bluetooth_sco"
            AudioDeviceInfo.TYPE_BLE_HEADSET -> "bluetooth_le"
            AudioDeviceInfo.TYPE_WIRED_HEADPHONES, AudioDeviceInfo.TYPE_WIRED_HEADSET -> "wired_headphones"
            AudioDeviceInfo.TYPE_USB_HEADSET -> "usb_headset"
            AudioDeviceInfo.TYPE_BUILTIN_SPEAKER, AudioDeviceInfo.TYPE_BUILTIN_EARPIECE -> "phone_speaker"
            null -> "none"
            else -> "other"
        }
        val scoActive = am.mode == AudioManager.MODE_IN_COMMUNICATION && if (Build.VERSION.SDK_INT >= 31) {
            am.communicationDevice?.type.let { it == AudioDeviceInfo.TYPE_BLUETOOTH_SCO || it == AudioDeviceInfo.TYPE_BLE_HEADSET }
        } else {
            @Suppress("DEPRECATION") am.isBluetoothScoOn
        }
        val input = when {
            inputs.isEmpty() -> "none"
            scoActive -> "bluetooth_mic"
            inputs.any { it.type == AudioDeviceInfo.TYPE_WIRED_HEADSET } -> "headset_mic"
            inputs.any { it.type == AudioDeviceInfo.TYPE_USB_HEADSET || it.type == AudioDeviceInfo.TYPE_USB_DEVICE } -> "usb_mic"
            inputs.any { it.type == AudioDeviceInfo.TYPE_BUILTIN_MIC } -> "phone_mic"
            else -> "other"
        }
        return AudioRoute(input, output, media?.productName?.toString()?.takeIf { outType in PRIVATE_TYPES },
            privateOutputPresent = outType in PRIVATE_TYPES, couplesInputAndOutput = output == "bluetooth_sco" || scoActive)
    }

    companion object {
        val PRIVATE_TYPES = setOf(
            AudioDeviceInfo.TYPE_BLUETOOTH_A2DP, AudioDeviceInfo.TYPE_BLUETOOTH_SCO, AudioDeviceInfo.TYPE_BLE_HEADSET,
            AudioDeviceInfo.TYPE_WIRED_HEADPHONES, AudioDeviceInfo.TYPE_WIRED_HEADSET, AudioDeviceInfo.TYPE_USB_HEADSET,
        )
    }
}
