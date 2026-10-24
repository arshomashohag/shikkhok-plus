package com.shikkhokplus.app.feature.fees.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.fees.ClaimRow

/** Stable test identifiers. Not user-visible text. */
const val TAG_CLAIMS_LIST: String = "claims_list"

/** One claim. */
const val TAG_CLAIM_ROW: String = "claim_row"

/** One claim's server-set status. */
const val TAG_CLAIM_STATUS: String = "claim_status"

/** The approved amount, present once a teacher has decided. */
const val TAG_CLAIM_APPROVED: String = "claim_approved"

/** The shortfall disposition, where one applies. */
const val TAG_CLAIM_DISPOSITION: String = "claim_disposition"

/** The notice that a verification was corrected. */
const val TAG_CLAIM_CORRECTION: String = "claim_correction"

/** The explanation shown when nothing has been claimed. */
const val TAG_CLAIMS_EMPTY: String = "claims_empty"

/**
 * What happened to the payments this person reported.
 *
 * **The rejection the submitter must see** [BR5.6] and **the prior
 * decision a correction retained** [BR5.7] are both rendered here. A
 * rejection the submitter never sees leaves them believing they paid;
 * a correction hidden from the person whose money it concerns is the
 * exact asymmetry FR9.2 forbids, and the mapper sets
 * `correctionNoticeKey` so this screen cannot omit it by accident.
 *
 * **No composable here compares a domain value.** `isDecided` is a
 * mapper field derived from the status enum, not a test of whether
 * `approvedAmount` is null — those differ for a rejection, which is
 * decided and has no approved amount.
 *
 * @param rows The claims, as the mapper produced them
 * @param modifier Layout modifier
 */
@Composable
fun ClaimStatusScreen(
    rows: List<ClaimRow>,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (rows.isEmpty()) {
            Text(
                stringResource(R.string.claims_empty),
                Modifier.testTag(TAG_CLAIMS_EMPTY),
            )
            return@Column
        }

        LazyColumn(
            modifier = Modifier.testTag(TAG_CLAIMS_LIST),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(rows, key = { it.claimId }) { row -> ClaimDetailRow(row) }
        }
    }
}

/**
 * One claim and its outcome.
 *
 * @param row The claim to render
 */
@Composable
private fun ClaimDetailRow(row: ClaimRow) {
    Column(
        modifier = Modifier.fillMaxWidth().testTag(TAG_CLAIM_ROW),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Text(row.period, style = MaterialTheme.typography.titleSmall)
        Text(
            stringResource(
                R.string.claim_claimed_amount,
                Numerals.money(row.claimedAmount),
                row.channelLabel,
            ),
        )
        Text(
            stringResource(MessageKeys.resolve(row.statusLabel)),
            modifier = Modifier.testTag(TAG_CLAIM_STATUS),
        )

        // `isDecided` rather than `approvedAmount != null`: a REJECTED
        // claim is decided and carries no approved amount, so the
        // nullable test would render it as still pending.
        if (row.isDecided && row.approvedAmount != null) {
            Text(
                stringResource(
                    R.string.claim_approved_amount,
                    Numerals.money(row.approvedAmount),
                ),
                modifier = Modifier.testTag(TAG_CLAIM_APPROVED),
            )
        }
        if (row.dispositionLabel != null) {
            Text(
                stringResource(MessageKeys.resolve(row.dispositionLabel)),
                modifier = Modifier.testTag(TAG_CLAIM_DISPOSITION),
            )
        }
        if (row.correctionNoticeKey != null) {
            Text(
                stringResource(MessageKeys.resolve(row.correctionNoticeKey)),
                modifier = Modifier.testTag(TAG_CLAIM_CORRECTION),
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}
