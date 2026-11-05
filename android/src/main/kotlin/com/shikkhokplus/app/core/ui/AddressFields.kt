package com.shikkhokplus.app.core.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.model.PostalAddress

/** The house or flat field. */
const val TAG_ADDRESS_HOUSE: String = "address_house"

/** The road or area field. */
const val TAG_ADDRESS_ROAD: String = "address_road"

/** The city or district field. */
const val TAG_ADDRESS_CITY: String = "address_city"

/** The postcode field. */
const val TAG_ADDRESS_POSTCODE: String = "address_postcode"

/**
 * The four address fields, on sign-up and on Edit profile.
 *
 * All four are required (decided 2026-11-05). The postcode says so as
 * soon as something other than four digits is typed; an empty field
 * says nothing until the person tries to go on.
 *
 * @param address What is typed
 * @param onChange Called with the address after each edit
 * @param modifier The layout modifier
 * @param showMissing Whether to name the parts still empty
 */
@Composable
fun AddressFields(
    address: PostalAddress,
    onChange: (PostalAddress) -> Unit,
    modifier: Modifier = Modifier,
    showMissing: Boolean = false,
) {
    val required = stringResource(R.string.address_required)
    fun missing(part: String) = required.takeIf { showMissing && part.isBlank() }
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        ShikkhokTextField(
            value = address.house,
            onValueChange = { onChange(address.copy(house = it)) },
            label = stringResource(R.string.address_house_label),
            error = missing(address.house),
            fieldModifier = Modifier.testTag(TAG_ADDRESS_HOUSE),
        )
        ShikkhokTextField(
            value = address.road,
            onValueChange = { onChange(address.copy(road = it)) },
            label = stringResource(R.string.address_road_label),
            error = missing(address.road),
            fieldModifier = Modifier.testTag(TAG_ADDRESS_ROAD),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            ShikkhokTextField(
                value = address.city,
                onValueChange = { onChange(address.copy(city = it)) },
                label = stringResource(R.string.address_city_label),
                error = missing(address.city),
                modifier = Modifier.weight(1f),
                fieldModifier = Modifier.testTag(TAG_ADDRESS_CITY),
            )
            val postcodeTyped = address.postcode.isNotBlank()
            ShikkhokTextField(
                value = address.postcode,
                onValueChange = { onChange(address.copy(postcode = it)) },
                label = stringResource(R.string.address_postcode_label),
                error =
                    when {
                        postcodeTyped && !PostalAddress.postcodeIsValid(address.postcode) ->
                            stringResource(R.string.address_postcode_invalid)
                        else -> missing(address.postcode)
                    },
                keyboardType = KeyboardType.Number,
                modifier = Modifier.weight(1f),
                fieldModifier = Modifier.testTag(TAG_ADDRESS_POSTCODE),
            )
        }
    }
}
