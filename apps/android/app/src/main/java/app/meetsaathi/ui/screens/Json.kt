package app.meetsaathi.ui.screens

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.longOrNull

/** Tolerant readers for read-mostly views so the UI accepts additive server fields. */
fun JsonObject.str(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content?.takeIf { it.isNotEmpty() }
fun JsonObject.arr(k: String): JsonArray? = this[k] as? JsonArray
fun JsonObject.obj(k: String): JsonObject? = this[k] as? JsonObject
fun JsonObject.bool(k: String): Boolean = (this[k] as? JsonPrimitive)?.booleanOrNull ?: false
fun JsonObject.long(k: String): Long? = (this[k] as? JsonPrimitive)?.longOrNull
val JsonElement.o: JsonObject get() = this as? JsonObject ?: JsonObject(emptyMap())
val JsonElement.text: String get() = (this as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content ?: ""
