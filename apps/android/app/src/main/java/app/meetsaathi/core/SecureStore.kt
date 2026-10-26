package app.meetsaathi.core

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** AES-256-GCM sealing. Format: 12-byte IV || ciphertext+tag. The key never leaves its provider. */
interface Sealer {
    fun seal(plain: ByteArray, aad: ByteArray): ByteArray
    fun open(sealed: ByteArray, aad: ByteArray): ByteArray
}

class AesGcmSealer(private val keyProvider: () -> SecretKey) : Sealer {
    override fun seal(plain: ByteArray, aad: ByteArray): ByteArray {
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.ENCRYPT_MODE, keyProvider())
        c.updateAAD(aad)
        return c.iv + c.doFinal(plain)
    }

    override fun open(sealed: ByteArray, aad: ByteArray): ByteArray {
        require(sealed.size > 12) { "sealed blob too short" }
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.DECRYPT_MODE, keyProvider(), GCMParameterSpec(128, sealed.copyOfRange(0, 12)))
        c.updateAAD(aad)
        return c.doFinal(sealed.copyOfRange(12, sealed.size))
    }
}

/** Android Keystore-backed keys (hardware-backed where the device supports it). */
object KeystoreKeys {
    private const val STORE = "AndroidKeyStore"

    fun key(alias: String): SecretKey {
        val ks = KeyStore.getInstance(STORE).apply { load(null) }
        (ks.getKey(alias, null) as? SecretKey)?.let { return it }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, STORE)
        gen.init(
            KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return gen.generateKey()
    }

    fun delete(alias: String) {
        KeyStore.getInstance(STORE).apply { load(null) }.deleteEntry(alias)
    }
}

/** Encrypted small-value store for tokens and device id (never in plaintext SharedPreferences). */
class SecureStore(context: Context) {
    private val prefs = context.getSharedPreferences("ms_secure", Context.MODE_PRIVATE)
    private val sealer = AesGcmSealer { KeystoreKeys.key("ms_tokens_v1") }

    fun put(name: String, value: String?) {
        if (value == null) {
            prefs.edit().remove(name).apply(); return
        }
        val sealed = sealer.seal(value.toByteArray(), name.toByteArray())
        prefs.edit().putString(name, Base64.encodeToString(sealed, Base64.NO_WRAP)).apply()
    }

    fun get(name: String): String? = prefs.getString(name, null)?.let {
        runCatching { String(sealer.open(Base64.decode(it, Base64.NO_WRAP), name.toByteArray())) }.getOrNull()
    }

    fun clearTokens() {
        prefs.edit().remove("access").remove("refresh").apply()
    }
}
