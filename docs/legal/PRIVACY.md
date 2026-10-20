# ShikhokPlus Privacy Policy

**Last updated: 20 October 2026**

ShikhokPlus (`com.shikkhokplus.app`) helps private tutors in
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

ShikhokPlus is used by school-age students, so children's data is
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

## How long we keep it

| Data | Kept for |
|---|---|
| One-time codes | 5 minutes, then deleted |
| Failed sign-in attempts | 30 days |
| Sign-in rate counters | 24 hours |
| Sign-in audit log (no names, no codes) | 12 months |
| Session tokens | 30 days, or until you sign out |
| Your account and profile | Until you delete it |
| Class records | Until the teacher deletes them, or per the rules below |

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

**Deleted permanently, within 30 days:**

- Your phone number
- Your name and profile photo
- Your sign-in history and session tokens
- Any note or detail you entered about yourself

**Kept, but no longer identifying you:**

- Attendance, marks and fee entries a teacher recorded remain in that
  teacher's class history, with your name and contact details removed.
  The teacher sees an unnamed former-student row.

**Why we keep that.** The entries are simultaneously your personal
data and the teacher's record of a class they ran and were paid for.
Erasing them would rewrite a teacher's attendance history and fee
ledger — including payments already settled. Removing everything that
identifies you, while leaving the anonymous record, is how we honour
your erasure right without destroying someone else's records.

If you want the anonymised entries removed as well, ask us and we will
discuss it with the teacher concerned.

### A teacher deleting their account

A teacher's deletion removes their own phone number, name and profile
on the same terms. Their students' records are deleted with the class,
since nobody else holds them.

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
