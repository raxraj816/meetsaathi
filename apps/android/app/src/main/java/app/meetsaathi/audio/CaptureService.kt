package app.meetsaathi.audio

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import app.meetsaathi.MainActivity
import app.meetsaathi.MeetSaathiApp
import app.meetsaathi.R

/**
 * Microphone foreground service (Android FGS type "microphone"). It is started only from the visible activity
 * after an explicit Start (Android 12+ forbids background starts), shows a persistent neutral notification,
 * and owns the AudioRecord lifetime. Stopping it releases the microphone immediately.
 */
class CaptureService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                (application as MeetSaathiApp).container.live.endFromNotification()
                return START_NOT_STICKY
            }
        }
        ensureChannel(this)
        val type = if (Build.VERSION.SDK_INT >= 30) ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE else 0
        try {
            ServiceCompat.startForeground(this, NOTIF_ID, notification(this, paused = false), type)
        } catch (e: Exception) {
            // ForegroundServiceStartNotAllowedException / missing permission: report truthfully, never capture.
            (application as MeetSaathiApp).container.live.onCaptureFailure("BACKGROUND_RESTRICTED")
            stopSelf()
            return START_NOT_STICKY
        }
        (application as MeetSaathiApp).container.live.onServiceForeground()
        // Never restart capture silently after the OS kills the process (UNI-004): NOT_STICKY.
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        (application as MeetSaathiApp).container.live.onServiceDestroyed()
        super.onDestroy()
    }

    companion object {
        const val CHANNEL = "ms_capture"
        const val NOTIF_ID = 41
        const val ACTION_STOP = "app.meetsaathi.STOP_CAPTURE"

        fun start(ctx: Context) {
            ctx.startForegroundService(Intent(ctx, CaptureService::class.java))
        }

        fun stop(ctx: Context) {
            ctx.stopService(Intent(ctx, CaptureService::class.java))
        }

        fun ensureChannel(ctx: Context) {
            val nm = ctx.getSystemService(NotificationManager::class.java)
            if (nm.getNotificationChannel(CHANNEL) == null) {
                nm.createNotificationChannel(NotificationChannel(CHANNEL, ctx.getString(R.string.notif_channel_capture),
                    NotificationManager.IMPORTANCE_LOW).apply { lockscreenVisibility = Notification.VISIBILITY_PRIVATE })
            }
        }

        fun notification(ctx: Context, paused: Boolean): Notification {
            val open = PendingIntent.getActivity(ctx, 0, Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
                PendingIntent.FLAG_IMMUTABLE)
            val stop = PendingIntent.getService(ctx, 1, Intent(ctx, CaptureService::class.java).setAction(ACTION_STOP),
                PendingIntent.FLAG_IMMUTABLE)
            return NotificationCompat.Builder(ctx, CHANNEL)
                .setSmallIcon(R.drawable.ic_logo)
                .setContentTitle(ctx.getString(R.string.notif_capture_title))
                .setContentText(ctx.getString(if (paused) R.string.notif_paused_text else R.string.notif_capture_text))
                .setOngoing(true)
                .setVisibility(NotificationCompat.VISIBILITY_PRIVATE) // no conversation detail on the lock screen
                .setContentIntent(open)
                .addAction(0, ctx.getString(R.string.action_stop), stop)
                .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
                .build()
        }
    }
}
