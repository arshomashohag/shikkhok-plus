# The Bangla layout check

**Decided 2026-10-22.** The obligation is affirmed —
*"ALWAYS externalize user-facing strings with Bangla and English present from
the start, and verify that longer Bangla text does not break the layout"*
[TC-15, D-43] — and until today it had **no verifier at all**. Both string
bundles are complete at 53 entries each, which the build checks; nothing
checked the layout.

`team.md` names two acceptable verifiers: Compose screenshot tests at the
longest Bangla string, or an explicit per-screen manual check. **The manual
check is the one chosen**, on 2026-10-22.

## What makes this honest rather than a wish

A manual check depends on someone doing it, which is the failure mode this
project's practices usually design against. Three things are done here to
narrow that gap, and it is worth being plain that they narrow it rather than
close it:

1. **The table below is the artifact.** A screen with no row is a visible
   gap in a committed file, not a thing someone forgot. A unit is not
   complete while a screen it ships has no row.
2. **The check names the exact string to test with**, so "I looked at it"
   becomes "I rendered the longest Bangla string in this screen's longest
   field". Those are different claims.
3. **A failing row stays in the table with its finding.** Rows are not
   deleted when they fail; they are marked and fixed, so the table records
   what broke as well as what passed.

What this does not do: catch a regression. A screen that passed in D1 and
breaks in D4 is found only if someone re-checks it. That is the real cost of
choosing the manual option, and it is accepted deliberately rather than
hidden. If it bites, the escalation is the screenshot-test option, which the
practice already permits without re-deciding anything.

## How to run the check

For each screen, on a device or emulator in Bangla locale:

1. Set the device language to **বাংলা (বাংলাদেশ)**.
2. Open the screen with **real data at its longest realistic values** — a
   full Bangla name, a full batch name, a four-digit fee with the `৳` prefix.
3. Look for the four failure shapes:
   - **Truncation** — text cut with an ellipsis where the English fits.
   - **Overflow** — text escaping its container or overlapping a neighbour.
   - **Wrapping** — a label that was one line in English becoming three and
     pushing the layout.
   - **Clipping of Bangla glyph marks** — conjuncts and the ি / ী / ু vowel
     signs extend above and below the Latin line box, and a container sized
     to Latin metrics clips them. This is the Bangla-specific one and the
     easiest to miss, because the text is readable at a glance and wrong on
     inspection.
4. Record the row.

## Longest-string reference

The longest entries in `values-bn/strings.xml` at the time of each check.
Re-derive rather than trusting this list once strings change:

```
python3 - <<'EOF'
import re, pathlib
p = pathlib.Path("android/src/main/res/values-bn/strings.xml")
rows = re.findall(r'<string name="([^"]+)">(.*?)</string>', p.read_text(), re.S)
for name, text in sorted(rows, key=lambda r: -len(r[1]))[:10]:
    print(f"{len(text):4d}  {name}")
EOF
```

## The table

**Status values**: `PASS`, `FAIL (<what broke>)`, `FIXED (<what was done>)`.
A screen may appear more than once — a later unit re-checking it adds a row
rather than editing the old one.

| Unit | Screen | Artboard | Checked on | Longest string used | Status |
|---|---|---|---|---|---|
| — | Auth: phone entry | `O2` | *not yet checked* | | |
| — | Auth: OTP entry | `O3` | *not yet checked* | | |
| — | Batch list | `T6` | *not yet checked* | | |
| — | Roster | `T7` | *not yet checked* | | |
| D1 | Signup | `O1` | *not yet checked* | `signup_already_added_notice` (88) | |
| D1 | Invitations | `O4` | *not yet checked* | `invitations_empty_body` (104) | |
| D1 | Decline sheet — student | `O4` | *not yet checked* | `decline_student_body` (106) | |
| D1 | Decline sheet — guardian | `O4` | *not yet checked* | `decline_guardian_body` (125) | |
| D1 | Profile (edit half) | `O5` | *not yet checked* | `profile_teacher_name_note` (105) | |
| D2 | Batch list (with the count) | `T6` | *not yet checked* | `roster_accepted_count` (33) | |
| D2 | Roster (per-link states, declined mark) | `T7` | *not yet checked* | `roster_declined_mark` (31) | |
| D2 | Add student | `T8` | *not yet checked* | `student_add_guardian_hint` (61) | |
| D2 | Create batch | — | *not yet checked* | `batch_create_created` (18) | |
| D2 | Remove seat (confirm + two refusals) | — | *not yet checked* | `roster_remove_claimed_remedy` (145) | |
| D2 | Guardian child home | `G1` | *not yet checked* | `guardian_empty_body` (96) | |
| D3 | Fee history (student and guardian) | `G3` | *not yet checked* | `fees_empty` (25) | |
| D3 | Batch fees (what each student owes) | `T5`, `S2` | *not yet checked* | `batch_fees_empty` (31) | |
| D3 | Payment form | `S3` | *not yet checked* | `payment_ask_teacher` (93) | |
| D3 | Claim outcomes (incl. the correction notice) | `T4`, `G3` | *not yet checked* | `fees_claim_corrected` (34) | |
| D4 | Session list (today's and past classes) | `T1` | *not yet checked* | `sessions_empty` (32) | |
| D4 | Session detail with the roster (attendance marking) | `T2` | *not yet checked* | `attendance_queued` (74) | |
| D4 | **Conflict resolution (two rosters side by side)** | `T2` | *not yet checked* | `attendance_version_conflict` (122) | |
| D4 | Exam list | `T3` | *not yet checked* | `exam_entered_count` (43) | |
| D4 | Mark entry | `T3` | *not yet checked* | `mark_entry_locked` (40) | |
| D4 | Marksheet (student and guardian) | `G4` | *not yet checked* | `marksheet_no_comparison` (45) | |
| D4 | Guardian progress over time | `G4` | *not yet checked* | `progress_title` (14) | |
| D5 | **Teacher overview (earnings, trend, next exam)** | `T6` | *not yet checked* | `dues_nobody_owes` (86) / `overview_earnings_label` (16) | |
| D5 | Cross-batch dues list | `T5` | *not yet checked* | `dues_nobody_owes` (86) | |
| Design parity | More — teacher, student, guardian (profile card, section headers, rows) | `T9`, `S4`, `G4` | *not yet checked* | `more_invitations_sub_guardian` (45) | |
| Design parity | Edit profile | `S4` | *not yet checked* | `profile_teacher_name_note` (105) | |
| Design parity | Log out sheet (with and without unsent records) | `T9` | *not yet checked* | `log_out_unsent_body` (44) | |
| Design parity | My children | `G4` | *not yet checked* | `my_children_note` (100) | |
| Design parity | Offline banner and withheld fee (Today, Dues, My batches, Inside a batch, guardian home, More) | `T1`, `T5`, `S1`, `S2`, `G1`, `T9` | *not yet checked* | `family_offline_body` (78) / `family_fee_unavailable_body` (78) | |
| Design parity | Guardian home's pinned switcher and child header | `G1` | *not yet checked* | `guardian_payments_unavailable` (57) | |
| Design parity | Add student's "Batch fee" toggle | `T8` | *not yet checked* | `student_add_batch_fee_help` (39) | |
| Design parity | Settings (notifications, theme, text size) | `T9`, `S4`, `G4` | *not yet checked* | `settings_notifications_sub` (65) | |
| Design parity | Address in four parts (sign-up, Edit profile) | `O1`, `S4` | *not yet checked* | `address_required` / `address_postcode_invalid` | |
| Design parity | Guardian invitation names the child | `G4` | *not yet checked* | `invitation_child_yes` | |
| Design parity | Mark entry: publish bar and decimal key | `T3`, `T7` | *not yet checked* | `mark_entry_published` / `mark_entry_publish` | |
| Record payment | Teacher's "Record payment" sheet (fee history), short amount showing carry-or-waive | `T5` | *not yet checked* | `fees_record_reference` (33) / `verify_carry_forward_body` | |
| Exam cancel | "Cancel exam" confirmation on mark entry, and the Cancelled chip on the Exams tab | `T3`, `T7` | *not yet checked* | `exam_cancel_confirm_body` (102) | |
| Inbox | Payment recorded and exam cancelled items, and the cancelled exam's detail | `S4`, `G4` | *not yet checked* | `marks_exam_published` (61) / `inbox_payment_recorded_body` (43) | |
| Help centre | My questions (status labels, new-reply mark, empty state with Ask a question) and the More row | — | *not yet checked* | `help_empty_body` (88) / `help_status_answered` (19) beside `help_new_reply` (10) | |
| Help centre | Ask a question (privacy hint, subject and question with counters, failed-send banner) | — | *not yet checked* | `help_ticket_too_many` (95) / `help_privacy_hint` (72) | |
| Help centre | Question thread (bubbles signed `help_from_support`, closed notice, reply box) | — | *not yet checked* | `help_closed_notice` (56) / `help_from_support` (19) | |
| Two-step verification | Sign-in second step: authenticator code boxes, "Use a recovery code instead", recovery-code field with Continue, wrong-code and lock messages | `O3` | *not yet checked* | `two_step_signin_recovery_body` (110) / `mfa_challenge_expired` (66) / `two_step_use_app` (37) | |
| Two-step verification | More row with the "Recommended" badge, and the status page (on/off card, required or recommended line, codes left, few-codes warning, Turn on / New recovery codes / Turn off) | `T9`, `S4`, `G4` | *not yet checked* | `two_step_intro` (149) / `two_step_codes_low_body` (82) / `more_two_step_sub` (35) beside `two_step_recommended` (10) | |
| Two-step verification | Turn on: "Open authenticator app", the no-app message, setup key in groups of four with Copy, first-code boxes | — | *not yet checked* | `two_step_no_app` (138) / `two_step_setup_step1` (71) | |
| Two-step verification | Recovery codes shown once (ten codes, "won't be shown again", Copy all, "I've saved them"; new-codes variant with the old-codes notice) | — | *not yet checked* | `two_step_codes_body` (125) / `two_step_codes_old_stopped` (36) | |
| Two-step verification | Turn off (app code or recovery code) and New recovery codes | — | *not yet checked* | `two_step_renew_body` (87) / `two_step_off_body` (84) | |
| Two-step verification | The one-time offer sheet after sign-in (teachers and centre members only) | — | *not yet checked* | `two_step_offer_body` (107) / `two_step_offer_title` (52) | |
| U3 | Auth: sign-in with one login field (phone, email or username) and the email-shape message under it | `O2` | *not yet checked* | `auth_login_label` (22) | |
| U3 | Auth: OTP entry, replacement-username state (title, body, field with hint, Continue) | `O3` | *not yet checked* | `auth_replace_username_body` (107) / `account_username_invalid_character` (58) | |
| U3 | Signup: username field, helper and availability hint in every state (checking, available, taken, could not check) | `O1` | *not yet checked* | `account_username_invalid_character` (58) / `signup_username_help` (50) / `username_could_not_check` (50) | |
| U3 | Choose username (the gate: title, body, field with hint, Continue, Sign out) | — | *not yet checked* | `choose_username_body` (94) | |
| U3 | More: Username and Phone and email rows | `T9`, `S4`, `G4` | *not yet checked* | `more_contacts_sub_none` (27) / `more_username_choose` (22) | |
| U3 | Username (view, change, changed with its date, change-too-soon banner) | — | *not yet checked* | `username_rule_note` (97) / `account_username_change_too_soon` (55) / `username_changed_on` (51) | |
| U3 | Phone and email (both cards present; one absent; the password note) | — | *not yet checked* | `contacts_password_note` (52) | |
| U3 | Replace contact (entry step and code step) | — | *not yet checked* | `contacts_replaced_email` (65) / `account_contact_change_limit` (64) | |
| U3 | Remove contact sheet, including the last-one refusal | — | *not yet checked* | `contacts_remove_body` (110) / `account_contact_last_one` (90) | |
| U3 | Add student: student email and guardian email fields | `T8` | *not yet checked* | `student_email_taken` (38) / `student_add_student_email` (26) | |
| U3 | Edit student dialog: student email and guardian email fields | — | *not yet checked* | `student_email_taken` (38) / `student_add_student_email` (26) | |
| U3 | Student detail and student list: email shown in place of a missing phone | — | *not yet checked* | `student_number_erased` (81) / `student_number_accepted` (72), with a 40-character email as the contact line | |
| U3 | Roster row: guardian email in place of a missing phone | `T7` | *not yet checked* | no new string; a 40-character guardian email as the contact line beside a full Bangla name | |
| U3 | Centre members: invite by phone or email, and a member with an email only | — | *not yet checked* | `centre_member_already_invited` (43) / `centre_invite_by_help` (39) | |
| U4 (web) | Sign-in: one login field, its `email.invalid` message and the wrong-password banner | `web` | *not yet checked* | `web_auth_signin_body` (66) / `web_auth_password_wrong_hint` (66) / `auth_login_label` (22) | |
| U4 (web) | Sign-up: username field and every hint state (checking, available, unavailable, invalid, could not check) | `web` | *not yet checked* | `web_auth_signup_email_help` (101) / `account_username_invalid_character` (58) / `username_could_not_check` (50) | |
| U4 (web) | Code step: Replace username state, sign-up and code flow | `web` | *not yet checked* | `web_auth_replace_username_body_plain` (118) / `auth_replace_username_body` (106) | |
| U4 (web) | Choose username (the gate: title, body, field with hint, Continue, Sign out) | `web` | *not yet checked* | `choose_username_body` (94) | |
| U4 (web) | Settings → Account: Username and Phone and email rows | `web` | *not yet checked* | `more_contacts_sub_none` (27) / `more_username_choose` (22) | |
| U4 (web) | Username: view, change, changed with its date, change too soon | `web` | *not yet checked* | `username_rule_note` (97) / `account_username_change_too_soon` (55) / `username_changed_on` (50) | |
| U4 (web) | Contacts: both present; one absent; the password note | `web` | *not yet checked* | `contacts_password_note` (52) | |
| U4 (web) | Replace contact: entry and code steps | `web` | *not yet checked* | `contacts_replaced_email` (65) / `account_contact_change_limit` (64) / `account_contact_password_required` (64) | |
| U4 (web) | Remove contact sheet, including the last-one refusal | `web` | *not yet checked* | `contacts_remove_body` (109) / `account_contact_last_one` (90) | |
| U4 (web) | New student: two email fields | `web` | *not yet checked* | `web_auth_email_invalid` (48) / `student_email_taken` (38) / `student_add_student_email` (26) | |
| U4 (web) | Student Edit sheet | `web` | *not yet checked* | `student_number_erased` (81) / `student_number_accepted` (72) / `web_student_edit_saved` (23) | |
| U4 (web) | Student detail and list: email in place of a phone | `web` | *not yet checked* | `web_students_col_phone` (19), with a 40-character email as the contact line | |
| U4 (web) | Batch roster: guardian email; contact column header; quick-add link | `web` | *not yet checked* | `roster_declined_no_number` (40) / `web_students_add_by_email` (28) / `web_roster_col_contact` (18) | |
| U4 (web) | Auth side panel (`AuthFrame`): reworded `web_auth_point_login` | `web` | *not yet checked* | `web_auth_point_login` (70) | |
| U4 (web) | Password (set and change): reworded `web_password_set_body` | `web` | *not yet checked* | `web_password_set_body` (83) | |
| U4 (web) | Add phone or email: reworded `web_contact_add_*_why` | `web` | *not yet checked* | `web_contact_add_phone_why` (143) / `web_contact_add_email_why` (100) | |
| U4 (web) | Edit profile: reworded `web_contact_add_phone_why` | `web` | *not yet checked* | `web_contact_add_phone_why` (143) | |
| U4 (web) | Failed start card with Sign out | `web` | *not yet checked* | `error_unexpected` (54) / `more_log_out` (6) | |
| U4 (web) | Root error card (a page that failed to render) | `web` | *not yet checked* | `error_unexpected` (54) / `auth_retry` (16) | |
| U4 (web) | Centre members: invite by phone or email; a member with an email only | `web` | *not yet checked* | `centre_member_already_invited` (43) / `centre_invite_by_help` (39) | |
| H4 (web) | MyReviews: the guardian home's Reviews row, and the list (batch title, owner's public name, state chip with "From {date}") | `web` | *not yet checked* | `hub_reviews_empty` (38) / `hub_reviews_entry_guardian_sub` (35) / `hub_reviews_state_reviewed` beside a full Bangla batch title | |
| H4 (web) | ReviewEditor: five labelled star radios, body with its 1000 counter, the privacy note, status chip with a reason, "edit until", the not-yet banner with its date, the read-only review with Delete, and the delete confirmation, and the "cannot be written now" banner (`hub_review_unavailable`, 36) | `web` | *not yet checked* | `hub_review_privacy_note` (116) / `hub_review_needs_attendance` (75) / `hub_review_not_yet_eligible` (69) / `hub_review_status_not_published` with `hub_review_reason_identifiable_child` (30) | |
| H4 (web) | Teacher Reviews (the listing editor's Reviews row, per-batch rating rows including the below-threshold line, review cards with tenure and month, reply box with counter and status, Delete reply, Report) | `web` | *not yet checked* | `hub_review_tenure_gt_1y` (46) / `hub_reviews_below_threshold` (42) / `hub_reviews_reply_note` (38) / `hub_reviews_entry_owner_sub` (37) | |
| H4 (web admin) | Admin Reviews tab (`web/src/admin/hub/Queue.tsx`, `ReviewRow.tsx`): author reference and role, tenure, rating, words, the review a reply answers, the checklist line, approve and reject with a code, the held notice | `web` | *not yet checked* | `web_admin_hub_review_check` (70) / `web_admin_hub_review_held` (31) | |
| H4 (public) | Hub batch page review section (`app/hub/public/templates/_reviews.html`): rating summary or the below-threshold line, the "most recent" line, review cards with tenure and month, the teacher's reply, the report links | `web` | *not yet checked* | `review_by_gt_1y` (46) / `reviews_below_threshold` (42) / `reviews_most_recent` (42) in `app/hub/public/messages.py` | |
| H4 (Android) | Guardian home's Reviews row (under every child, and on the no-children card) and MyReviews (`MyReviewsScreen`: batch title, owner's public name, state with "From {date}") | — | *not yet checked* | `hub_reviews_empty` (38) / `hub_reviews_entry_guardian_sub` (35) / `hub_reviews_state_reviewed` (19) beside a full Bangla batch title | |
| H4 (Android) | ReviewEditor (`ReviewEditorScreen`): five labelled star rows, the words field with its 1000 counter, the privacy note, status with a reason, "edit until", the not-yet banner with its date, the read-only review with Delete, the delete dialog, and the "cannot be written now" banner (`hub_review_unavailable`, 36) | — | *not yet checked* | `hub_review_privacy_note` (116) / `hub_review_needs_attendance` (75) / `hub_review_not_yet_eligible` (69) / `hub_review_status_not_published` with `hub_review_reason_identifiable_child` | |
| H4 (Android) | Teacher Reviews (`OwnerReviewsScreen`, and the listing editor's Reviews row): per-batch rating rows including the below-threshold line, review cards with tenure · month, reply field with note and counter, status, Send reply, Delete reply, Report | — | *not yet checked* | `hub_review_tenure_gt_1y` (46) / `hub_reviews_below_threshold` (42) / `hub_reviews_reply_note` (38) with the counter on one help line / `hub_reviews_entry_owner_sub` (37) | |
| H5 (web) | HubEnquiry (`/hub-enquiry`): "To {owner}" with the batch title, student name, class select, message with its 300 counter, the two share options with the help line, the declaration box, the three "required" lines, the refusal banner with "See my join requests", the sent banner, the already-open banner, and the unavailable line | `web` | *not yet checked* | `hub_enquiry_share_help` (128) / `hub_enquiry_already_open` (92) / `hub_enquiry_contains_contact` (88) / `hub_enquiry_sent` (76) / `hub_enquiry_declaration` (65) beside its checkbox / `hub_enquiry_share_email` (42) with a full Bangla owner name | |
| H5 (web) | MyEnquiries (`/hub-enquiries`, and More's "My join requests" row): owner name or the no-longer-listed fallback, batch title, student · class · "Sent {date}", the waiting chip or the answer line, "Call {number}", Withdraw on the same row, the withdraw confirmation, the failed-withdraw banner | `web` | *not yet checked* | `hub_enquiry_outcome_added` (49) / `hub_enquiry_withdraw_body` (38) / `hub_enquiry_mine_sub` (34) / `hub_enquiry_owner_unknown` (31) beside `hub_enquiry_withdraw` | |
| H5 (web) | Enquiries (`/more/hub/enquiries`, and the listing editor's "Receive join requests" switch and "Join requests" row): student name, class · batch · received time, the status chip | `web` | *not yet checked* | `hub_enquiry_switch_help` (101) / `hub_enquiry_inbox_sub` (47) / `hub_enquiry_answered_added` (32) as a chip at the row's end | |
| H5 (web) | EnquiryDetail (`/more/hub/enquiries/:id`), and the add-student form opened from it: the six labelled fields, "Not shared", the three answer buttons on one row, the refused-answer banner, the prefilled note and the saved-but-not-answered banner with Retry | `web` | *not yet checked* | `hub_enquiry_saved_not_closed` (85) / `hub_enquiry_prefilled` (72) / `hub_enquiry_action_add` (26) beside `hub_enquiry_action_call_us` and `hub_enquiry_action_not_now` | |
| H5 (Android) | EnquiryForm (`EnquiryFormScreen`, opened from the "Ask to join" App Link): "To {owner}" with the batch title, student name, the class picker, message with its 300 counter, the two share options with the help line, the declaration row, the refusal banner with Retry or "See my join requests", the sent banner, the already-open banner, the unavailable banner (`hub_enquiry_off`, 35) and the invalid-link banner | — | *not yet checked* | `hub_enquiry_share_help` (128) / `hub_enquiry_already_open` (92) / `hub_enquiry_contains_contact` (88) / `hub_enquiry_sent` (76) / `hub_enquiry_declaration` (65) beside its checkbox / `hub_enquiry_share_email` (43) with a full Bangla owner name | |
| H5 (Android) | MyEnquiries (`MyEnquiriesScreen`, and More's "My join requests" row): owner name or the no-longer-listed fallback, batch title, student · class · "Sent {date}", the waiting line or the answer line, "Call {number}", Withdraw, the withdraw dialog, the failed-withdraw banner with Retry, the "withdrawn" notice, the could-not-refresh banner above kept rows | — | *not yet checked* | `hub_enquiry_outcome_added` (49) / `hub_enquiry_withdraw_body` (38) / `hub_enquiry_mine_sub` (34) / `hub_enquiry_owner_unknown` (31) | |
| H5 (Android) | OwnerEnquiries (`OwnerEnquiriesScreen`, and the listing editor's "Receive join requests" switch card with its failure banner and "Join requests" row): student name, class · batch · received time, the status at the row's end, the unavailable banner, the could-not-refresh banner above kept rows | — | *not yet checked* | `hub_enquiry_switch_help` (101) beside the switch / `hub_enquiry_inbox_sub` (47) / `hub_enquiry_answered_added` (32) at the row's end beside a full Bangla student name | |
| H5 (Android) | OwnerEnquiryDetail (`OwnerEnquiryDetailScreen`), and the add-student form opened from it: the labelled fields, the call or email action or "Not shared", the answer buttons stacked full width, the refused-answer banner with Retry, the "answer sent" notice, the prefilled banner and the saved-but-not-answered banner with Retry | — | *not yet checked* | `hub_enquiry_saved_not_closed` (85) / `hub_enquiry_prefilled` (72) / `hub_enquiry_action_add` (26) | |

**H5's four web rows (2026-11-20) are open, and nothing automated
discharges them.** The Vitest tests Task 8 added (`HubEnquiry.test.tsx`,
`MyEnquiries.test.tsx`, `Enquiries.test.tsx`) are correctness tests that
assert what each state renders and what reaches the server; they measure no
layout. Lengths are code points from the regenerated
`web/src/i18n/generated/strings.bn.json`, placeholders unfilled. The row to
check first is HubEnquiry: `hub_enquiry_share_help` (119) sits under two
radio labels that each carry the owner's public name, and the declaration
(65) is a checkbox label. Class levels reuse the listing editor's
`web_hub_level_*` words. **The Bangla copy itself is awaiting the human
Bangla review**; a reworded string re-opens its row. Task 9 adds the Android
rows, with the same strings.

**H5's four Android rows (2026-11-20) are open, and nothing automated
discharges them.** The Robolectric tests Task 9 added
(`HubEnquiryRouteTest`, `HubEnquiryScreensTest`, `InboxRouteTest`) assert
what each state renders, what reached the server and which screen opened;
they measure no layout. Lengths are code points from `values-bn/strings.xml`,
placeholders unfilled. Task 9 reworded two shared strings,
`hub_enquiry_contains_contact` and `hub_enquiry_share_help`, so their web row
is re-opened with the new lengths. The Android row to check first is
EnquiryForm: `hub_enquiry_share_help` (128) sits under two radio rows that
each carry the owner's public name, and the declaration (65) is a checkbox
row's label. The counter under the message takes Latin digits through
`Numerals.count`. **The Bangla copy itself is awaiting the human Bangla
review.**

**H4's three Android rows (2026-11-19) are open, and nothing automated
discharges them.** The Robolectric tests Task 12 added (`HubReviewsRouteTest`,
`InboxRouteTest`) drive the routes and assert what reached the server and which
screen opened; they measure no layout. The strings are the web rows' strings,
shared through `strings.xml`, with the same lengths. The Android row to check
first is the teacher Reviews card: `hub_reviews_reply_note` and the `0/1000`
counter share one help line under the reply field, which the web draws as two
spans on one row.

**H4's five rows (2026-11-19) are open, and nothing automated discharges
them.** The Vitest tests H4 added (`reviews.test.tsx`, `Reviews.test.tsx`)
are correctness tests that assert what each state renders and measure no
layout. Lengths are code points from the regenerated
`web/src/i18n/generated/strings.bn.json`, `web/src/admin/i18n/admin.bn.json`
and `app/hub/public/messages.py`, placeholders unfilled. The row to check
first is ReviewEditor: `hub_review_privacy_note` (116) sits under a
textarea and above the submit button, and the five star labels are radios
whose Bangla adjectives are longer than the English. The admin row and the
public row were built by Tasks 7 and 9 and are added here because this is
the unit's edit to this file. **The Bangla copy itself is awaiting the
human Bangla review** recorded for H4; a reworded string re-opens its row.

**U4's twenty web rows (2026-11-15) are open, and nothing automated
discharges them.** No screenshot test or browser layout harness exists in
`web/`, and none was added; the Vitest tests U4 added are correctness tests
that assert what each state renders and measure no layout. The lengths are
code points, computed from the regenerated `web/src/i18n/generated/strings.bn.json`
and the `web/src/i18n/web/*.bn.json` bundles with placeholders unfilled, not
estimated. Check each row in a browser with the app's language set to
বাংলা, at a 360 CSS px viewport and again at the wide layout (`useWide`),
at the default text size, and record the string used and a `PASS`,
`FAIL (…)` or `FIXED (…)` status. The rows to check first: Add phone or
email, whose reworded `web_contact_add_phone_why` (143) is the longest
string any U4 screen shows and sits in a Settings row's subtitle as well as
under the field; and the Replace step from the code flow, whose plain body
(118) sits above a field whose hint grows when a name is refused.

**U3's fourteen rows (2026-11-15) are open, and nothing automated discharges
them.** The Robolectric tests added by U3 assert what each state renders and
which screen the root routes to; they are correctness tests and measure no
layout. Lengths above were computed from `values-bn/strings.xml` with the
snippet under "Longest-string reference", not estimated. The row to check
first is the remove-contact sheet: `contacts_remove_body` (110) is the
longest U3 string and sits in a dialog beside a password field and two
buttons. The verify replacement is second: `auth_replace_username_body`
(107) sits above a field whose hint grows to two lines when a name is
refused. Two rows show contact values the
person typed rather than strings from the bundle; check them with a long
email, because an email has no break opportunity before its `@` and is the
likeliest thing in U3 to overflow a row. Usernames and emails are Latin text
inside a Bangla layout by nature, which is the intended result.

**U3's timed hint check (performance NFR8.4) is also manual, and nothing
automated discharges it.** No Macrobenchmark harness exists, and the unit
tests on the availability checker test the client's debounce, timeout and
cache logic, not the device's latency. On the pilot's low-end device, on a
mobile network, time from the pause that ends the debounce to the hint
showing an answer or "could not check"; the target is within 1 second.

| Screen | Device | Network | Observed times (five pauses) | Status |
|---|---|---|---|---|
| Signup: username field | *not yet checked* | | | |
| Choose username (gate) | *not yet checked* | | | |
| Username: change | *not yet checked* | | | |
| Auth: OTP entry, replacement username | *not yet checked* | | | |

**U4's timed hint check on the web (performance NFR8.4) is manual too, and
nothing automated discharges it.** No browser performance harness exists in
`web/`, and the Vitest tests on the availability checker run under fake
timers: they test the client's debounce, 3 s bound and cache logic, not
real latency. In a browser on the pilot's low-end Android phone, on a
mobile network, time from the pause that ends the debounce to the hint
showing an answer or "could not check"; the target is within 1 second.

| Screen | Browser | Device | Network | Observed times (five pauses) | Status |
|---|---|---|---|---|---|
| U4 (web) Sign-up: username field | *not yet checked* | | | | |
| U4 (web) Choose username (gate) | *not yet checked* | | | | |
| U4 (web) Username: change | *not yet checked* | | | | |

**The three help-centre rows (2026-11-07) are open on the same terms**:
nothing automated discharges them; the Robolectric screen tests assert
what each state renders in English and say nothing about Bangla layout.
The row to watch is My questions: each question's status label sits on
one line beside the bold "new reply" mark, so `help_status_answered`
(19) and `help_new_reply` (10) together must stay readable at a large
font scale. On Ask a question, `help_ticket_too_many` (95) lands as an
error banner between the question field and Send, so check it does not
push Send below the fold with the keyboard open. Lengths computed from
`values-bn/strings.xml` with the snippet above.

**The six two-step verification rows (2026-11-07) are open on the same
terms**: nothing automated discharges them. The Robolectric tests in
`TwoStepScreenTest` and `AuthSecondStepScreenTest` assert what each state
renders in English, and that the recovery-code screen sets `FLAG_SECURE`;
they say nothing about Bangla layout. Rows to watch: on the More row the
"Recommended" badge (`two_step_recommended`, 10) sits at the row's end
beside a two-line title and sub-label, and must not squeeze the sub-label
to one word per line at a large font scale; on Turn on, the setup key is
monospace and must wrap by group rather than mid-group on a narrow phone,
with `two_step_no_app` (138) pushing the code boxes down; on the recovery
codes screen, check that "I've saved them" is reachable by scrolling with
all ten codes shown. Lengths computed from `values-bn/strings.xml` with
the snippet above.

**D4's seven rows are open, and nothing automated discharges them.**
The obligation is a check on a device in Bangla locale [team: Testing
Posture], there is still no screenshot harness in this project, and
code generation cannot perform one. Stated plainly because a manual
verifier described without that sentence reads, to the next person, as
a verifier [project.md, learned 2026-10-23]. BR7.5 makes a screen with
no row an incomplete unit; these rows exist so the gap is a visible
line in a committed file.

**D5's two rows are open on the same terms**, and the same sentence
applies to them: nothing automated discharges either. D5 added no
screenshot harness, because the human closed that choice on 2026-10-23
in favour of the manual per-screen check, and a correctness test does
not discharge a layout obligation [project.md].

**The eleven design-parity rows (2026-11-04) are open on the same terms**:
nothing automated discharges them. The More rows are the ones to watch —
each row's title and grey sub-label sit beside a 22dp icon and a chevron
in a 360dp-wide card, so a long Bangla sub-label wraps rather than
truncates, and the row must grow with it (`heightIn`, never a fixed
height). Lengths computed from `values-bn/strings.xml` with the snippet
above.

**The teacher overview is D5's first row to check**, and the reason is
density rather than length. `overview_earnings_label` is only 16
characters, but it sits *directly above a money amount rendered in
Bangla numerals* — and that pairing is the densest short string in the
product. Bangla conjuncts and the ি / ী / ু vowel signs extend above
and below the Latin line box, so a headline-sized figure under a label
in a container sized to Latin metrics is exactly the clipping case the
check exists to find. It is also the screen a teacher opens most.

The lengths were **computed from `values-bn/strings.xml` after this
unit's strings landed**, by running the snippet above rather than
estimating. **Both bundles stand at 245 entries**, of which D5 added 10
to each — counted on 2026-10-25 with
`grep -c "<string " android/src/main/res/values{,-bn}/strings.xml`, and
equal on both sides, which is the property that matters. (An earlier
revision of this sentence said 223; that figure predated D4's strings
reaching the working tree and was never recounted. Where a document
states a number, the number is a claim [project.md].)

**The conflict-resolution screen is the first row to check, and by some
distance.** Three things compound on it, and no other screen in the
product carries all three:

- `attendance_version_conflict` at **122 characters is the third-longest
  string in the whole bundle**, behind only
  `roster_remove_claimed_remedy` (145) and `decline_guardian_body`
  (125). It is a two-clause sentence and it sits *above* the comparison
  rather than replacing it, so unlike those two it does not have the
  panel to itself.
- The screen then renders **two labelled columns of names side by side**
  on a phone — the densest Bangla text this unit ships [BR7.5]. Each
  cell is a weighted half of a `Row`, so a long Bangla name wraps inside
  its own half rather than clipping; what the check must confirm is that
  the wrap is *readable*, not merely that nothing is cut.
- The two column headings (`conflict_mine_heading`,
  `conflict_theirs_heading`) must stay visually parallel. If one wraps
  to two lines and the other does not, the columns stop reading as a
  comparison, which is the one thing this screen exists to communicate.

The whole screen scrolls vertically, so the failure to look for is
**wrapping and glyph clipping rather than being pushed below the fold**.

**A second D4 row carries a check the others do not: the queued
notice.** `attendance_queued` (74) and the four `queue_state_*` strings
are the only copy in the product that has to make an unsent write read
as *unsent*. BR3.1's whole guarantee is that a queued roster never
renders as confirmed, and in Bangla the risk is specific: if
`queue_state_queued` ("এই ফোনে আছে, এখনও পাঠানো হয়নি") is truncated at
the comma, what remains reads as "it is on this phone" — which a teacher
would reasonably take as saved. **A checker must confirm these four
strings are not truncated**, and that `queue_state_failed` and
`queue_state_conflicted` remain visibly different sentences rather than
both collapsing to an ellipsis [AC3.1.10]. Truncation here is not a
cosmetic fault; it is the silent-queue failure arriving through the
layout.

**One thing a well-meaning checker must not "fix" on the marksheet
rows.** `marksheet_rank` and `exam_entered_count` reorder their two
placeholders relative to the English (`%2$s জনের মধ্যে %1$s তম`,
`%2$s-এর মধ্যে %1$s জনের`), the same shape as D3's two amount strings.
Reversing them would read as the wrong rank or the wrong count, not as
a layout fault, and nothing automated would catch it. Marks render
through `Numerals.marks` and counts through `Numerals.count`, so
**Latin digits inside Bangla text is the intended result** here exactly
as it is for money.

**D3's four rows are open for the same reason the eleven above are, and
two of them carry a check the others do not.**

The lengths were **computed from `values-bn/strings.xml` at the time of
writing**, not taken from the reference list below and not estimated.
This project's memory records a stage whose table asserted figures were
measured when they were not, so the method is stated rather than
implied.

**The payment form is the row to check first.** `payment_ask_teacher`
at 93 characters is the copy shown *instead of* the destination step
where a teacher set no collection number [NFR14.34], so it lands in the
space a number and a channel list would otherwise occupy — the most
variable vertical space on any D3 screen. A checker should confirm it
does not push the amount field below the fold on a small device.

**Two D3 rows need a check nothing else in this table has needed: the
digits inside them must stay Latin.** Every amount on these screens is
rendered through `Numerals.money`, and the server's `Money.format`
agrees [BR6.6] — so `৳1,25,400` is the intended result in Bangla, with
Bengali text around Latin digits and a Bengali taka sign. Three specific
things to confirm, each of which a well-meaning fix would break:

- `fees_outstanding_of_charged` renders **two** amounts in one sentence
  (`%2$s-এর মধ্যে %1$s বাকি`), with the placeholders in the opposite
  order to the English. A reversed pair would read as the wrong figure
  owed, not as a layout fault, and nothing automated would catch it.
- `claim_claimed_amount` likewise reorders its two placeholders
  (`%2$s-এ %1$s`), putting the channel before the amount.
- Lakh grouping (`1,25,400`, not `125,400`) must survive, because
  Western grouping reads as a different magnitude to a Bangladeshi
  reader.

**A checker who "corrects" any of those three is breaking the rule
rather than the layout**, which is the same warning the accepted-count
row below carries.

**Nothing automated discharges these four rows.** The obligation is a
check on a device in Bangla locale [team: Testing Posture], there is
still no screenshot harness in the project, and code generation cannot
perform one. Stated plainly because a manual verifier described without
that sentence reads, to the next person, as a verifier [project.md,
learned 2026-10-23].

**D2's six rows are open for the same reason D1's five are**, and they
are added here with the exact string each check must use so the gap is a
visible line in a committed file rather than an omission.

**Two of D2's rows deserve naming before anyone runs them.**

`roster_remove_claimed_remedy` at **145 characters is now the longest
string in the whole bundle**, displacing `decline_guardian_body` (125).
Re-derived at the time of writing rather than taken from the reference
list. It is a three-clause sentence sitting in a refusal panel beside a
title and two buttons, which is where wrapping and glyph-clipping
failures are most likely. **It is the first D2 row to check.**

The batch-list and roster rows carry a failure mode the other rows do
not: **`roster_accepted_count` is the one count in the product with no
locale helper between the server and the screen** [NFR3.3]. Money goes
through `Numerals.money`, marks through `Numerals.marks`; this string
formats two bare integers through `Numerals.count`, which renders them
Latin by the project's own numeral rule. What the check must confirm is
that "9 of 12 accepted" reads correctly in Bangla with **Latin digits
inside Bangla text**, which is the intended and slightly unusual
result — and that the sentence does not wrap badly when both numbers
reach three digits. A checker who "fixes" this by converting the digits
would be breaking the rule, not the layout.

**D1's five rows are open, and that is the accurate record.** The
obligation this table exists to carry is a check **on a device in Bangla
locale** [team: Testing Posture], and code generation cannot perform one:
nothing automated discharges it, which is the sentence this project
requires to be written rather than implied [project.md, learned
2026-10-23]. The rows are added now, with the exact string each check must
use, so the gap is a visible line in a committed file rather than an
omission — which is what the table was created to make impossible.

**D1's strings are now the four longest in the whole bundle**, re-derived
at the time of writing rather than taken from the reference list below.
`decline_guardian_body` at 125 characters is the longest string in the
app, and it sits in a bottom sheet beside a title and two buttons — the
tightest vertical space in the product. That is where the wrapping and
glyph-clipping failures are most likely, and it is the first row to check.

The five rows are a D1 obligation that is **not discharged**; see the
Gaps section of this unit's `code-summary.md`.

The four rows above are the screens that **already shipped** without this
check existing. They are listed as outstanding rather than assumed good:
three Android Bolts merged before the obligation had a verifier, so nothing
establishes that they pass. Checking them is part of D1, alongside the
screens D1 adds.

### Screens still to come

Added to the table by the unit that ships them. From the approved plan:

- **D1** — `O1` create account, in all five states; the pending-seat list
- **D2** — `T7` roster with pending state, `T8` add student, create batch,
  remove student, `G1` guardian child home
- **D3** — `T5` dues, `S2` batch fees, `T4` verify, `S3` submit, `G3` history
- **D4** — *added to the table above.* The plan named four screens
  (`T1` today, `T2` record a class, `T3` mark entry, marksheet); the
  unit ships **seven**, because the conflict-resolution screen, the
  exam list and guardian progress are each their own screen rather than
  states of another. BR7.5 enumerates all seven by name and a screen
  with no row means an incomplete unit, so the table carries seven rows
  rather than the four forecast here.
- **D5** — *added to the table above.* The plan forecast "insights" as
  one screen; the unit ships **two**, because the cross-batch dues list
  and the teacher overview are different screens with different refresh
  patterns rather than two states of one [functional-spec § 7a].
- **D6** — deletion confirmation and its copy
