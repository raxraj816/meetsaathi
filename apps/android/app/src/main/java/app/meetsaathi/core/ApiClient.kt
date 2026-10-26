package app.meetsaathi.core

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.IOException
import java.util.UUID
import java.util.concurrent.TimeUnit

class ApiException(val status: Int, val error: ApiErrorBody) : Exception(error.userMessage)
class OfflineException(cause: Throwable) : IOException("Network unavailable", cause)

interface TokenProvider {
    var accessToken: String?
    var refreshToken: String?
    var deviceId: String?
}

class SecureTokenProvider(private val store: SecureStore) : TokenProvider {
    override var accessToken: String? get() = store.get("access"); set(v) = store.put("access", v)
    override var refreshToken: String? get() = store.get("refresh"); set(v) = store.put("refresh", v)
    override var deviceId: String? get() = store.get("device"); set(v) = store.put("device", v)
}

/**
 * REST client for the MeetSaathi API. Every mutation carries an Idempotency-Key so retries after a network
 * flap can never double-apply (master 10). Errors are surfaced in the standard contract shape.
 */
class ApiClient(
    val baseUrl: String,
    private val tokens: TokenProvider,
    val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS).readTimeout(60, TimeUnit.SECONDS).writeTimeout(30, TimeUnit.SECONDS)
        .pingInterval(20, TimeUnit.SECONDS).build(),
) {
    private val json = "application/json".toMediaType()
    private val refreshLock = Mutex()
    var onSignedOut: (() -> Unit)? = null

    val isSignedIn: Boolean get() = tokens.accessToken != null

    suspend fun <T> call(method: String, path: String, body: String?, out: KSerializer<T>?, idempotent: Boolean = false,
                         idempotencyKey: String? = null, auth: Boolean = true): T? = withContext(Dispatchers.IO) {
        send(method, path, body, idempotent, idempotencyKey, auth).use { r ->
            val text = r.body?.string().orEmpty()
            if (out == null || text.isBlank()) null else WireJson.decodeFromString(out, text)
        }
    }

    /** Authenticated binary GET (evidence audio). Same refresh / sign-out semantics as [call]. */
    suspend fun bytes(path: String): ByteArray = withContext(Dispatchers.IO) {
        send("GET", path, null, idempotent = false, idempotencyKey = null, auth = true).use { r -> r.body?.bytes() ?: ByteArray(0) }
    }

    /** Executes with one refresh-and-replay on 401; returns only successful responses, otherwise throws [ApiException]. */
    private suspend fun send(method: String, path: String, body: String?, idempotent: Boolean, idempotencyKey: String?, auth: Boolean): Response {
        val key = if (idempotent) (idempotencyKey ?: "and-" + UUID.randomUUID()) else null
        val failedToken = tokens.accessToken
        var resp = execute(method, path, body, key, auth)
        if (resp.code == 401 && auth && refresh(failedToken)) {
            resp.close()
            resp = execute(method, path, body, key, auth) // same key: safe replay
        }
        if (resp.isSuccessful) return resp
        resp.use { r ->
            val text = r.body?.string().orEmpty()
            val err = runCatching { WireJson.decodeFromString(ApiErrorBody.serializer(), text) }
                .getOrDefault(ApiErrorBody(code = "HTTP_${r.code}", userMessage = ""))
            if (r.code == 401 && auth) {
                tokens.accessToken = null; tokens.refreshToken = null; onSignedOut?.invoke()
            }
            throw ApiException(r.code, err)
        }
    }

    private fun execute(method: String, path: String, body: String?, key: String?, auth: Boolean): Response {
        val b = Request.Builder().url(baseUrl.trimEnd('/') + path)
        if (auth) tokens.accessToken?.let { b.header("Authorization", "Bearer $it") }
        key?.let { b.header("Idempotency-Key", it) }
        val rb = body?.toRequestBody(json) ?: if (method == "POST" || method == "PUT" || method == "PATCH") "{}".toRequestBody(json) else null
        b.method(method, rb)
        return try {
            http.newCall(b.build()).execute()
        } catch (e: IOException) {
            throw OfflineException(e)
        }
    }

    private suspend fun refresh(failedToken: String?): Boolean = refreshLock.withLock {
        if (tokens.accessToken != null && tokens.accessToken != failedToken) return true
        val rt = tokens.refreshToken ?: return false
        val r = try {
            execute("POST", "/v1/auth/refresh", WireJson.encodeToString(RefreshIn.serializer(), RefreshIn(rt)), null, auth = false)
        } catch (e: OfflineException) {
            return false
        }
        r.use {
            if (!it.isSuccessful) return false
            val t = WireJson.decodeFromString(Tokens.serializer(), it.body!!.string())
            tokens.accessToken = t.accessToken
            tokens.refreshToken = t.refreshToken
            return true
        }
    }

    // ---- typed helpers ---------------------------------------------------------------------------------------
    suspend inline fun <reified I, T> post(path: String, input: I, out: KSerializer<T>, idempotent: Boolean = true): T =
        call("POST", path, WireJson.encodeToString(kotlinx.serialization.serializer<I>(), input), out, idempotent)!!

    suspend fun <T> get(path: String, out: KSerializer<T>): T = call("GET", path, null, out)!!

    suspend fun register(email: String, password: String, name: String?, deviceName: String, ageConfirmed: Boolean) {
        val t = call("POST", "/v1/auth/register", WireJson.encodeToString(RegisterIn.serializer(),
            RegisterIn(email, password, name, DeviceIn(name = deviceName), ageConfirmed)), Tokens.serializer(), auth = false)!!
        store(t)
    }

    suspend fun login(email: String, password: String, deviceName: String) {
        val t = call("POST", "/v1/auth/login", WireJson.encodeToString(LoginIn.serializer(),
            LoginIn(email, password, DeviceIn(name = deviceName, deviceId = tokens.deviceId))), Tokens.serializer(), auth = false)!!
        store(t)
    }

    private fun store(t: Tokens) {
        tokens.accessToken = t.accessToken
        tokens.refreshToken = t.refreshToken
        t.deviceId?.let { tokens.deviceId = it }
    }

    suspend fun reauth(password: String) {
        val body = buildJsonObject { put("password", password) }.toString()
        val t = call("POST", "/v1/auth/reauth", body, Tokens.serializer())!!
        tokens.accessToken = t.accessToken
    }

    suspend fun logout() {
        runCatching { call<Unit>("POST", "/v1/auth/logout", null, null) }
        tokens.accessToken = null; tokens.refreshToken = null
    }

    suspend fun raw(method: String, path: String, body: JsonObject? = null, idempotent: Boolean = false): JsonObject? =
        call(method, path, body?.toString(), JsonObject.serializer(), idempotent)

    fun accessTokenForRealtime(): String? = tokens.accessToken

    suspend fun prepareRealtimeAuth() { call<Unit>("GET", "/v1/me", null, null) }
    fun deviceId(): String? = tokens.deviceId
}
