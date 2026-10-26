package app.meetsaathi

import android.app.Application
import app.meetsaathi.audio.EvidencePlayer
import app.meetsaathi.core.ApiClient
import app.meetsaathi.core.LiveSessionController
import app.meetsaathi.core.SecureStore
import app.meetsaathi.core.SecureTokenProvider

class AppContainer(val app: Application) {
    val secure = SecureStore(app)
    val api = ApiClient(BuildConfig.API_BASE_URL, SecureTokenProvider(secure))
    val live = LiveSessionController(app, api)
    val evidence = EvidencePlayer(app, api).also { it.purgeCache() }
}

class MeetSaathiApp : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
        // Never auto-starts capture: this only drains already-permitted spooled audio (UNI-004, CON-015).
        if (container.api.isSignedIn) container.live.recoverSpools()
    }
}
