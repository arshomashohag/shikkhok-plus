package com.shikkhokplus.app.feature.hublisting

import com.shikkhokplus.app.core.network.OpenApi
import com.shikkhokplus.app.feature.hublisting.ui.curriculumLabel
import com.shikkhokplus.app.feature.hublisting.ui.levelLabel
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.intOrNull
import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * The hub editor offers exactly the server's vocabularies and limits.
 *
 * Read from the committed `openapi.json`, which the server's schema-diff
 * gate keeps equal to what it generates: a class level the server would
 * refuse, or a text box longer than the column, fails here rather than as
 * a refusal the owner reads.
 */
class HubVocabularyContractTest {

    private fun schema(name: String): JsonObject =
        OpenApi.spec["components"]!!.jsonObject["schemas"]!!.jsonObject[name]!!.jsonObject

    private fun property(model: String, field: String): JsonObject =
        schema(model)["properties"]!!.jsonObject[field]!!.jsonObject

    private fun enumOf(node: JsonObject): List<String> {
        val resolved = OpenApi.resolve(node)
        resolved["const"]?.let { return listOf(it.jsonPrimitive.content) }
        return resolved["enum"]?.jsonArray?.map { it.jsonPrimitive.content }.orEmpty()
    }

    private fun arms(node: JsonObject): List<JsonObject> =
        node["anyOf"]?.jsonArray?.map { it.jsonObject } ?: listOf(node)

    private fun maxLength(model: String, field: String): Int? =
        arms(property(model, field)).firstNotNullOfOrNull { it["maxLength"]?.jsonPrimitive?.intOrNull }

    @Test
    fun `class levels are the servers vocabulary`() {
        // The committed document lists an enum sorted; the editor's order is
        // a teacher's, so the two are compared as sets.
        val items = arms(property("BatchListingUpdateRequest", "class_levels")).first { it["items"] != null }
        val offered = ClassLevel.entries.map { it.wire }
        assertEquals(enumOf(items["items"]!!.jsonObject).toSet(), offered.toSet())
        assertEquals(offered.size, offered.toSet().size)
    }

    @Test
    fun `curricula are the servers vocabulary plus clearing it`() {
        val offered = arms(property("BatchListingUpdateRequest", "curriculum")).flatMap { enumOf(it) }
        assertEquals(offered.toSet(), Curriculum.entries.map { it.wire }.toSet() + "")
    }

    @Test
    fun `text limits are the servers`() {
        val owner = "OwnerListingUpdateRequest"
        val batch = "BatchListingUpdateRequest"
        val expected =
            mapOf(
                (owner to "public_name") to HubLimits.PUBLIC_NAME,
                (owner to "slug") to HubLimits.SLUG,
                (owner to "headline_en") to HubLimits.HEADLINE,
                (owner to "headline_bn") to HubLimits.HEADLINE,
                (owner to "bio_en") to HubLimits.BIO,
                (owner to "bio_bn") to HubLimits.BIO,
                (owner to "qualifications") to HubLimits.QUALIFICATIONS,
                (owner to "street_address") to HubLimits.STREET,
                (owner to "public_contact_phone") to HubLimits.PHONE,
                (batch to "public_title") to HubLimits.PUBLIC_TITLE,
                (batch to "description_en") to HubLimits.DESCRIPTION,
                (batch to "description_bn") to HubLimits.DESCRIPTION,
                (batch to "syllabus_en") to HubLimits.SYLLABUS,
                (batch to "syllabus_bn") to HubLimits.SYLLABUS,
            )
        expected.forEach { (where, limit) ->
            assertEquals(maxLength(where.first, where.second), limit, "${where.first}.${where.second}")
        }
    }
}

/** Every vocabulary entry has words, in both languages through the resources. */
class HubVocabularyLabelsTest {
    @Test
    fun `every class level and curriculum has a label`() {
        ClassLevel.entries.forEach { levelLabel(it) }
        Curriculum.entries.forEach { curriculumLabel(it) }
    }
}
