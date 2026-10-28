# ShikkhokPlus Privacy Policy

**Last updated: 20 October 2026**

ShikkhokPlus (`com.shikkhokplus.app`) helps private tutors in
Bangladesh manage their classes — attendance, marks and fees — and
lets students and guardians see their own records.

This policy describes what the app collects, why, and what happens
when you delete your account. It is written against the actual
database schema rather than in the abstract, so what it says and what
the code does cannot drift apart.

**Contact:** shohagsiraj.ru@gmail.com

---

## The short version

- We collect your **phone number**, your **name**, and the class
  records a teacher enters about a student — attendance, marks and
  fee payments.
- We do **not** collect any device or advertising identifier, we do
  **not** use analytics or advertising SDKs, and we do **not** sell
  or share your data with anyone.
- A teacher **cannot** see anything a student or guardian writes
  about themselves. That boundary is enforced by the database, not by
  our good intentions.
- You can delete your account from inside the app, or from a web page
  without installing anything.

---

## What we collect

### When you sign in

| Data | Why |
|---|---|
| Phone number | It is your account identity. There is no password. |
| One-time code | Sent by SMS to prove the number is yours. |

**You type your phone number.** The app never reads it from your SIM
or your device, and it never requests permission to read your SMS
messages. The one-time code is filled in automatically using Android's
SMS Retriever API, which lets the app read only our own message and
nothing else in your inbox.

The one-time code is stored only as an irreversible hash, exactly as a
password would be, and is deleted after a short period. We never log
it.

### When you use the app

| Data | Who enters it | Who can see it |
|---|---|---|
| Your own name and photo | You | Only you |
| Class name, schedule, fee amount | The teacher | The teacher, and enrolled students |
| Attendance and marks | The teacher | The teacher, and the student concerned |
| Fee payments and claims | The teacher and the student | Both parties to that fee |

### What we deliberately do not collect

This is not a list of things we have not got round to. Each is
blocked by an automated check that fails our build:

- **No advertising ID (AAID)**, and the app does not declare the
  permission that would allow one.
- **No device identifiers** — no IMEI, no SIM serial, no Android ID,
  no MAC or Wi-Fi address, no hardware serial.
- **No location**, at any precision.
- **No contacts, photos, files, camera or microphone access** beyond a
  profile picture you choose yourself.
- **No analytics or crash-reporting SDK** that transmits any of the
  above.

We verify this on every release by scanning the built app for those
identifiers, and by checking the final permission list against an
approved set. The only permission that grants the app access to
anything is **internet access**. The list may also contain a
self-scoped entry that Android libraries define on our own app — these
grant nothing and exist to stop other apps talking to ours.

---

## Children's data

ShikkhokPlus is used by school-age students, so children's data is
central rather than incidental.

- A child's record is created by their **teacher**, in the course of
  running a class the family has enrolled in.
- A guardian can be linked to a child's account and can see that
  child's attendance, marks and fees.
- **We show no advertising**, of any kind, to anyone.
- **We do not profile** children or build behavioural models.
- There is no public profile, no messaging between users, and no
  user-generated content visible to strangers.

If you are a parent or guardian and want to see, correct or delete
your child's data, contact us at the address above. If you believe a
child's data is in the app without a guardian's knowledge, tell us and
we will remove it.

---

## Who can see what

The separation below is enforced by the database itself — by row-level
security policies and by the fact that a teacher's view of the data is
built from different tables than a student's. It is not a filter in
application code that someone could forget to apply.

**A teacher can see** their own classes, the students enrolled in
them, and the attendance, marks and fees they themselves recorded.

**A teacher cannot see** a student's own profile, a guardian's
details, or anything a student or guardian writes about themselves.

**A student or guardian can see** their own profile, and their own
attendance, marks and fees.

**Nobody else can see anything.** There is no administrator view of
student data. Our own operational access is limited to subscriber
information — a teacher's name, plan and payment status.

---

## What we keep, and what deletion removes

The section below is **generated from the application's own data rules**
rather than written alongside them. Every row states what the code
actually does, and our build fails if the two stop matching.

<!-- BEGIN GENERATED: governance manifest -->

> This section is generated from the application's own data
> rules. If the code changes and this text is not regenerated,
> our build fails. It cannot quietly describe an older version.

### Deleted outright when you delete your account

| Data | Removed anyway after |
|---|---|
| A record that a teacher sent a fee reminder | 12 months |
| Failed and successful sign-in attempts | 7 days |
| Messages in your in-app inbox, such as a fee reminder | 12 months |
| One-time sign-in codes, stored only as hashes | 7 days |
| Session tokens, stored only as hashes | 30 days after it expires |
| Test-only message records, never used in production | 7 days |
| The record that you are a teacher | no time limit |
| Which classes you have hidden from your own view | no time limit |
| Your own name, photo and address | no time limit |
| Your phone number and account record | no time limit |

### Kept even after you delete your account, because the same record is someone else's too

| Data | Removed anyway after |
|---|---|
| A class a teacher runs | no time limit |
| A class that was held, on a date | no time limit |
| A class's weekly timetable | no time limit |
| A note a teacher posted to a class | no time limit |
| A payment you reported, and the teacher's decision on it | no time limit |
| A record that a teacher's entry was received | no time limit |
| A sign-in audit record carrying no name or code | 12 months |
| A student's exam result | no time limit |
| A student's place in a class, including the name the teacher typed | no time limit |
| A subject within a class | no time limit |
| Amounts charged, paid and waived | no time limit |
| An exam a teacher set | no time limit |
| The record that a fee was due for a month | no time limit |
| Whether a student attended a class | no time limit |

### Not about you, and not changed when you delete your account

These records are about how the service itself is running, not about any person. They hold no name, no phone number and nothing you wrote, and they are not linked to your account, so there is nothing in them for a deletion request to remove. We say so here rather than leaving them off the page: the counters below are what stop somebody flooding a phone number with sign-in codes, and clearing them on request would turn account deletion into a way of switching that protection off. Where the table below gives a time, the record clears itself after it; where it says there is no time limit, it is one line per scheduled job, overwritten on each run rather than appended to, so it never grows with the people using the service.

| Data | Removed anyway after |
|---|---|
| Counters that limit sign-in attempts | 48 hours |
| When our scheduled jobs last ran; it names nobody | no time limit |

**The name a teacher typed for you stays in that teacher's record.** When a teacher invites someone to a class they enter a name for that place themselves. That name belongs to the teacher's own record of the class, so it remains after you delete your account -- and it remains even if you declined the invitation and never used the app. It is not shown to anyone but that teacher. If you want it removed, contact us at the address at the top of this page and we will raise it with the teacher concerned.

<!-- governance manifest digest: 5237993ab8a1f4b65256fda9119921d2fd350d362caed3f083feef57ca0f52dd
     Covers every disposition, retention class and basis, so a
     change to any of them fails the drift gate even when it
     does not alter the text above. Regenerate; do not edit. -->
<!-- END GENERATED: governance manifest -->

---

## Deleting your account

**In the app:** Settings → Delete account.

**Without the app:** visit the deletion page linked from our Play
Store listing. You do not need to reinstall anything.

Either route asks you to confirm by signing in, so nobody else can
delete your account.

### What is deleted, exactly

This is the part most policies leave vague, and the part that matters
most. Deletion is not instant-everything: a teacher's record of a
class they taught is also their own business record.

**The precise answer, per kind of data, is in "What we keep, and what
deletion removes" above** — and it is generated from the code rather
than written here, so it cannot drift away from what actually happens.
This section explains the reasoning behind it.

**Why some records stay.** Attendance, marks and fee entries are
simultaneously your personal data and the teacher's record of a class
they ran and were paid for. Erasing them would rewrite a teacher's
attendance history and fee ledger — including payments already settled.
Keeping those entries, while removing everything of yours that we hold
on our own account, is how we honour your erasure right without
destroying someone else's records.

If you want entries like those removed as well, ask us and we will
discuss it with the teacher concerned.

---

## Where your data lives

On servers operated by Amazon Web Services. The database is encrypted
at rest, and all traffic between the app and our servers uses HTTPS.

We use one third-party service: an SMS gateway in Bangladesh, which
receives your phone number and the one-time code in order to send it.
It receives nothing else.

---

## Your rights

You can ask us to show you the data we hold about you, correct
anything wrong, delete your account, or export your records. Email the
address at the top of this page. We will respond within 30 days.

If you are in a jurisdiction with specific data-protection rights
(such as the UK or EU), those rights apply and this policy does not
limit them.

---

## Changes to this policy

We will update this page and change the date at the top. For a change
that materially affects what we collect or who can see it, we will
also notify you in the app before it takes effect.

---

## Security

- Phone numbers and one-time codes never appear in our logs.
- One-time codes and session tokens are stored only as irreversible
  hashes.
- Access to production data is restricted, named and logged.
- We never copy records containing a child's details into any external
  tool.
