package com.shikkhokplus.app.core.network

import kotlinx.serialization.descriptors.PolymorphicKind
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.descriptors.SerialKind
import kotlinx.serialization.descriptors.StructureKind
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import java.io.File

/**
 * The committed `openapi.json`, read for the contract gates.
 *
 * The server's schema-diff gate keeps that file equal to what the
 * server generates, so checking the app against it is checking the app
 * against the server.
 */
object OpenApi {

    /** Deeper than any body nests; a guard against a cycle. */
    private const val MAX_DEPTH = 12

    /** The whole document. */
    val spec: JsonObject by lazy {
        val file =
            generateSequence(File("").absoluteFile) { it.parentFile }
                .map { File(it, "openapi.json") }
                .first { it.exists() }
        Json.parseToJsonElement(file.readText()).jsonObject
    }

    private val schemas: JsonObject
        get() = spec["components"]!!.jsonObject["schemas"]!!.jsonObject

    /**
     * One operation, by method and path template.
     *
     * @param method `get`, `post`, `put`, `patch` or `delete`
     * @param path The server's path template
     * @return The operation, or null when the server has none
     */
    fun operation(method: String, path: String): JsonObject? =
        spec["paths"]!!.jsonObject[path]?.jsonObject?.get(method)?.jsonObject

    /**
     * The success status and its body schema, if any.
     *
     * @param operation An operation
     * @return The 2xx status, and its JSON schema or null for no body
     */
    fun success(operation: JsonObject): Pair<Int, JsonObject?> {
        val responses = operation["responses"]!!.jsonObject
        val status = responses.keys.first { it.startsWith("2") }
        val schema =
            responses[status]!!.jsonObject["content"]?.jsonObject
                ?.get("application/json")?.jsonObject?.get("schema")?.jsonObject
        return status.toInt() to schema
    }

    /**
     * The request body schema, if the operation takes one.
     *
     * @param operation An operation
     * @return Its JSON schema, or null
     */
    fun requestSchema(operation: JsonObject): JsonObject? =
        operation["requestBody"]?.jsonObject?.get("content")?.jsonObject
            ?.get("application/json")?.jsonObject?.get("schema")?.jsonObject

    /**
     * Follow a `$ref` to the schema it names.
     *
     * @param schema A schema node, possibly a reference
     * @return The schema it stands for
     */
    fun resolve(schema: JsonObject): JsonObject =
        schema["\$ref"]?.let { ref ->
            resolve(schemas[ref.jsonPrimitive.content.substringAfterLast('/')]!!.jsonObject)
        } ?: schema

    /**
     * The non-null arms of a schema: one for a plain schema, several
     * for a union.
     *
     * @param schema A schema node
     * @return Its resolved arms, without the `null` arm
     */
    fun arms(schema: JsonObject): List<JsonObject> {
        val resolved = resolve(schema)
        val union = resolved["anyOf"] ?: resolved["oneOf"]
        return union?.jsonArray
            ?.map { resolve(it.jsonObject) }
            ?.filter { it["type"]?.jsonPrimitive?.content != "null" }
            ?.flatMap(::arms)
            ?: listOf(resolved)
    }

    /**
     * An example value for one schema: required fields only, so the
     * app is held to what the server PROMISES rather than what it
     * might add.
     *
     * @param schema The schema node
     * @param depth Recursion guard
     * @return The example
     */
    fun example(schema: JsonObject, depth: Int = 0): JsonElement {
        check(depth < MAX_DEPTH) { "schema recursion too deep" }
        val arm = arms(schema).firstOrNull() ?: return JsonNull
        return when (arm["type"]?.jsonPrimitive?.content) {
            "object" -> {
                val properties = arm["properties"]?.jsonObject ?: JsonObject(emptyMap())
                val required = arm["required"]?.jsonArray?.map { it.jsonPrimitive.content }.orEmpty()
                buildJsonObject {
                    required.forEach { key -> put(key, example(properties[key]!!.jsonObject, depth + 1)) }
                    // A field with a default is not "required", but the
                    // server serializes it anyway -- the `published`
                    // discriminator among them -- so the app meets it.
                    properties.filterKeys { it !in required }.forEach { (key, property) ->
                        property.jsonObject["default"]?.let { put(key, it) }
                    }
                }
            }
            "array" -> buildJsonArray { add(example(arm["items"]!!.jsonObject, depth + 1)) }
            "integer" -> JsonPrimitive(1)
            "number" -> JsonPrimitive(1.5)
            "boolean" -> JsonPrimitive(true)
            "string" -> JsonPrimitive(sampleString(arm))
            null -> JsonObject(emptyMap())
            else -> error("unhandled schema type in $arm")
        }
    }

    /**
     * Every example of a schema: one per union arm.
     *
     * @param schema The schema node
     * @return Labelled examples
     */
    fun examples(schema: JsonObject): List<Pair<String, JsonElement>> =
        arms(schema).mapIndexed { index, arm -> "arm $index" to example(arm) }

    /**
     * A string the schema accepts.
     *
     * @param schema A string schema
     * @return A valid example string
     */
    private fun sampleString(schema: JsonObject): String =
        schema["enum"]?.jsonArray?.first()?.jsonPrimitive?.content
            ?: schema["const"]?.jsonPrimitive?.content
            ?: when {
                schema["pattern"]?.jsonPrimitive?.content == "^[0-9]+\\.[0-9]{2}$" -> "1200.00"
                schema["format"]?.jsonPrimitive?.content == "date" -> "2026-11-04"
                schema["format"]?.jsonPrimitive?.content == "date-time" -> "2026-11-04T10:00:00Z"
                schema["format"]?.jsonPrimitive?.content == "time" -> "16:00:00"
                schema["format"]?.jsonPrimitive?.content == "uuid" -> "00000000-0000-0000-0000-000000000001"
                else -> "x"
            }

    /**
     * Fields the app's type declares that the server's schema does not.
     *
     * **The half the decode check cannot see.** The app decodes with
     * `ignoreUnknownKeys` and gives most fields defaults, so a field
     * the server never sends decodes silently to its default — an
     * exam list reading "0 of 0" forever, say — and passes every
     * decode test. This walks the app's serial descriptor beside the
     * schema and names each such field.
     *
     * @param descriptor The app type's descriptor
     * @param schema The server's schema for the same value
     * @param at Where in the body, for the message
     * @return One message per field the server never sends
     */
    fun unknownFields(descriptor: SerialDescriptor, schema: JsonObject, at: String): List<String> {
        val arms = arms(schema)
        return when (descriptor.kind) {
            StructureKind.CLASS -> {
                val objects = arms.filter { it["type"]?.jsonPrimitive?.content == "object" }
                if (objects.isEmpty()) return emptyList()
                val properties =
                    objects.flatMap { arm ->
                        arm["properties"]?.jsonObject?.entries?.map { it.key to it.value.jsonObject }.orEmpty()
                    }.toMap()
                (0 until descriptor.elementsCount).flatMap { index ->
                    val name = descriptor.getElementName(index)
                    val property = properties[name]
                    if (property == null) {
                        listOf("$at.$name: the server never sends it")
                    } else {
                        unknownFields(descriptor.getElementDescriptor(index), property, "$at.$name")
                    }
                }
            }
            StructureKind.LIST -> {
                val items = arms.firstNotNullOfOrNull { it["items"]?.jsonObject }
                if (items == null) {
                    listOf("$at: the app reads a list where the server sends ${arms.map { it["type"] }}")
                } else {
                    unknownFields(descriptor.getElementDescriptor(0), items, "$at[]")
                }
            }
            is PrimitiveKind, SerialKind.ENUM, is PolymorphicKind, SerialKind.CONTEXTUAL,
            StructureKind.MAP, StructureKind.OBJECT,
            -> emptyList()
        }
    }

    /**
     * Check a request body against the schema the server validates it
     * with.
     *
     * The server's request models forbid extra fields, so an unknown
     * key is a 422 just as a missing required one is.
     *
     * @param body What the app sent
     * @param schema The server's request schema
     * @param at Where in the body, for the message
     * @return One message per violation
     */
    fun violations(body: JsonElement, schema: JsonObject, at: String = "body"): List<String> {
        val arms = arms(schema)
        if (body is JsonNull) {
            val nullable = (resolve(schema)["anyOf"]?.jsonArray ?: JsonArray(emptyList()))
                .any { it.jsonObject["type"]?.jsonPrimitive?.content == "null" }
            return if (nullable) emptyList() else listOf("$at: null where the server needs a value")
        }
        val failures = arms.map { arm -> violationsOfArm(body, arm, at) }
        return failures.firstOrNull { it.isEmpty() } ?: failures.first()
    }

    /**
     * Check a body against one non-union schema.
     *
     * @param body What the app sent
     * @param arm One resolved schema
     * @param at Where in the body
     * @return One message per violation
     */
    private fun violationsOfArm(body: JsonElement, arm: JsonObject, at: String): List<String> =
        when (arm["type"]?.jsonPrimitive?.content) {
            "object" -> {
                if (body !is JsonObject) {
                    listOf("$at: expected an object")
                } else {
                    val properties = arm["properties"]?.jsonObject ?: JsonObject(emptyMap())
                    val required = arm["required"]?.jsonArray?.map { it.jsonPrimitive.content }.orEmpty()
                    (required - body.keys).map { "$at.$it: required and not sent" } +
                        (body.keys - properties.keys).map { "$at.$it: the server does not accept it" } +
                        body.entries.filter { it.key in properties }.flatMap { (key, value) ->
                            violations(value, properties[key]!!.jsonObject, "$at.$key")
                        }
                }
            }
            "array" ->
                (body as? JsonArray)?.flatMapIndexed { index, item ->
                    violations(item, arm["items"]!!.jsonObject, "$at[$index]")
                } ?: listOf("$at: expected a list")
            "integer" ->
                if ((body as? JsonPrimitive)?.takeUnless { it.isString }?.longOrNull == null) {
                    listOf("$at: expected an integer")
                } else {
                    emptyList()
                }
            "boolean" ->
                if ((body as? JsonPrimitive)?.takeUnless { it.isString }?.booleanOrNull == null) {
                    listOf("$at: expected a boolean")
                } else {
                    emptyList()
                }
            "string" ->
                if ((body as? JsonPrimitive)?.isString != true) listOf("$at: expected a string") else emptyList()
            else -> emptyList()
        }
}
