"""The HTML part of the emailed code [0032].

Sent beside the plain-text part as ``multipart/alternative``, so a client
that cannot or will not render HTML still shows the code; the text part
stays the source of truth for the staging outbox.

**Nothing is fetched from anywhere.** No remote image, font or
stylesheet: a remote image in an email is a read receipt the reader
never agreed to, and the product promises no tracking. The wordmark is
type, the styles are inline, and the only URL is the Play Store link a
person may choose to follow.

**Inline styles and tables**, because that is what Gmail, Outlook and
the Android mail apps agree on. A ``<style>`` block carries only the
narrow-screen and dark-mode refinements, which clients that strip it
can do without.

**The code is escaped** at the one substitution site even though it is
always six digits, on the same reasoning as the deletion page: escaping
here is cheaper than proving it for every caller.

**The promotional block sits below the code and the safety note**, never
above: the person opened this email for the code, and an OTP email that
leads with marketing reads as phishing.
"""

from __future__ import annotations

import html
from string import Template
from typing import Final

__all__ = ["EMAIL_HTML_TEMPLATE", "PLAY_URL", "render_email_html"]

#: The Play listing. The package name is permanent [TC-2], so the URL is.
PLAY_URL: Final = "https://play.google.com/store/apps/details?id=com.shikkhokplus.app"

# ``string.Template`` rather than ``str.format``: CSS is full of braces.
EMAIL_HTML_TEMPLATE: Final = Template("""\
<!DOCTYPE html>
<html lang="bn">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<title>ShikkhokPlus কোড / code</title>
<style>
  @media (max-width: 600px) {
    .sp-pad { padding-left: 20px !important; padding-right: 20px !important; }
    .sp-code { font-size: 32px !important; letter-spacing: 8px !important; }
  }
  @media (prefers-color-scheme: dark) {
    .sp-page { background: #0f1215 !important; }
    .sp-card { background: #15191e !important; }
    .sp-ink { color: #e6e9ee !important; }
    .sp-soft { color: #b7bec9 !important; }
    .sp-box { background: #1e3f6e !important; }
    .sp-box-ink { color: #ffffff !important; }
    .sp-panel { background: #1c2128 !important; }
    .sp-rule { border-color: #2b313a !important; }
    .sp-accent { color: #a9c7ff !important; }
  }
</style>
</head>
<body class="sp-page" style="margin:0;padding:0;background:#f4f6f9;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">
কোডটি ৫ মিনিটের মধ্যে শেষ হবে · It expires in 5 minutes
</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
  border="0" class="sp-page" style="background:#f4f6f9;">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
  border="0" class="sp-card" style="max-width:560px;background:#ffffff;
  border-radius:12px;overflow:hidden;font-family:'Noto Sans Bengali',
  'Hind Siliguri','Noto Sans','Segoe UI',Roboto,Arial,sans-serif;">

<!-- Header: the wordmark is type, not an image. -->
<tr><td class="sp-pad" style="background:#1d4f91;padding:22px 32px;">
  <span style="font-size:22px;font-weight:700;color:#ffffff;
    letter-spacing:0.2px;">ShikkhokPlus</span>
  <span style="font-size:15px;color:#d8e3f7;padding-left:8px;">শিক্ষকপ্লাস</span>
</td></tr>

<!-- The code: the one thing this email exists to deliver. -->
<tr><td class="sp-pad" style="padding:32px 32px 8px;">
  <p class="sp-ink" style="margin:0;font-size:18px;font-weight:700;
    color:#15191f;line-height:1.5;">আপনার যাচাই কোড</p>
  <p lang="en" class="sp-soft" style="margin:2px 0 0;font-size:14px;
    color:#434a55;line-height:1.5;">Your verification code</p>
</td></tr>
<tr><td class="sp-pad" style="padding:16px 32px 8px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
    border="0"><tr>
    <td align="center" class="sp-box" style="background:#d8e3f7;
      border-radius:12px;padding:20px 12px;">
      <span class="sp-code sp-box-ink" style="font-family:'SFMono-Regular',
        Menlo,Consolas,'Liberation Mono',monospace;font-size:38px;
        font-weight:700;letter-spacing:12px;color:#0b2447;">${code}</span>
    </td>
  </tr></table>
</td></tr>
<tr><td class="sp-pad" style="padding:8px 32px 0;">
  <p class="sp-ink" style="margin:0;font-size:15px;color:#15191f;
    line-height:1.6;">কোডটি <strong>৫ মিনিটের</strong> মধ্যে শেষ হয়ে যাবে।
    কাউকে জানাবেন না — শিক্ষকপ্লাস কখনো আপনার কাছে কোড চাইবে না।</p>
  <p lang="en" class="sp-soft" style="margin:6px 0 0;font-size:14px;
    color:#434a55;line-height:1.6;">It expires in <strong>5 minutes</strong>.
    Do not share it &mdash; ShikkhokPlus will never ask you for it.</p>
</td></tr>
<tr><td class="sp-pad" style="padding:20px 32px 28px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
    border="0"><tr>
    <td class="sp-panel" style="background:#eef1f5;border-radius:8px;
      padding:12px 16px;">
      <p class="sp-soft" style="margin:0;font-size:13px;color:#434a55;
        line-height:1.6;">আপনি কোড না চেয়ে থাকলে এই ইমেইলটি উপেক্ষা করুন।</p>
      <p lang="en" class="sp-soft" style="margin:2px 0 0;font-size:13px;
        color:#434a55;line-height:1.6;">If you did not ask for a code, you
        can ignore this email.</p>
    </td>
  </tr></table>
</td></tr>

<!-- About ShikkhokPlus: below the code, never above it. -->
<tr><td class="sp-pad" style="padding:0 32px;">
  <div class="sp-rule" style="border-top:1px solid #c9ced6;"></div>
</td></tr>
<tr><td class="sp-pad" style="padding:24px 32px 4px;">
  <p class="sp-accent" style="margin:0;font-size:12px;font-weight:700;
    color:#1d4f91;
    letter-spacing:0.6px;text-transform:uppercase;">শিক্ষকপ্লাস সম্পর্কে
    <span lang="en">· About ShikkhokPlus</span></p>
  <p class="sp-ink" style="margin:8px 0 0;font-size:17px;font-weight:700;
    color:#15191f;line-height:1.5;">হাজিরা, নম্বর আর ফি — শিক্ষক ও কোচিং
    সেন্টারের জন্য</p>
  <p lang="en" class="sp-soft" style="margin:2px 0 0;font-size:14px;
    color:#434a55;line-height:1.5;">Attendance, marks and fees, for tutors
    and coaching centres</p>
</td></tr>
<tr><td class="sp-pad" style="padding:12px 32px 0;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
    border="0">
    <tr>
      <td width="28" valign="top" class="sp-accent" style="padding:6px 0;
        font-size:15px;color:#1d4f91;">&#10003;</td>
      <td style="padding:6px 0;">
        <p class="sp-ink" style="margin:0;font-size:14px;color:#15191f;
          line-height:1.5;">ব্যাচ, হাজিরা ও পরীক্ষার নম্বর এক জায়গায়</p>
        <p lang="en" class="sp-soft" style="margin:0;font-size:13px;
          color:#434a55;line-height:1.5;">Batches, attendance and exam marks
          in one place</p>
      </td>
    </tr>
    <tr>
      <td width="28" valign="top" class="sp-accent" style="padding:6px 0;
        font-size:15px;color:#1d4f91;">&#10003;</td>
      <td style="padding:6px 0;">
        <p class="sp-ink" style="margin:0;font-size:14px;color:#15191f;
          line-height:1.5;">মাসিক ফি, বকেয়া আর বিকাশ, নগদ বা ব্যাংক পেমেন্ট
          যাচাই</p>
        <p lang="en" class="sp-soft" style="margin:0;font-size:13px;
          color:#434a55;line-height:1.5;">Monthly fees, dues, and verifying
          bKash, Nagad or bank payments</p>
      </td>
    </tr>
    <tr>
      <td width="28" valign="top" class="sp-accent" style="padding:6px 0;
        font-size:15px;color:#1d4f91;">&#10003;</td>
      <td style="padding:6px 0;">
        <p class="sp-ink" style="margin:0;font-size:14px;color:#15191f;
          line-height:1.5;">শিক্ষার্থী ও অভিভাবক দেখেন ক্লাস, ফলাফল ও ফি</p>
        <p lang="en" class="sp-soft" style="margin:0;font-size:13px;
          color:#434a55;line-height:1.5;">Students and guardians see their
          classes, results and fees</p>
      </td>
    </tr>
  </table>
</td></tr>
<tr><td class="sp-pad" style="padding:14px 32px 0;">
  <p class="sp-soft" style="margin:0;font-size:13px;color:#434a55;
    line-height:1.6;">বিনা মূল্যে · বিজ্ঞাপন নেই, ট্র্যাকিং নেই · বাংলা ও
    <span lang="en">English</span><br>
    <span lang="en">Free &middot; No ads, no tracking &middot; Android
    and web</span></p>
</td></tr>
<tr><td class="sp-pad" style="padding:20px 32px 32px;">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
    <td align="center" style="background:#1d4f91;border-radius:12px;">
      <a href="${play_url}" style="display:inline-block;padding:10px 28px;
        font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;
        line-height:1.4;">Google Play থেকে নিন<br><span lang="en"
        style="font-size:12px;font-weight:400;color:#d8e3f7;">Get it on
        Google Play</span></a>
    </td>
  </tr></table>
</td></tr>

<!-- Footer -->
<tr><td class="sp-pad sp-panel" style="background:#eef1f5;padding:18px 32px;">
  <p class="sp-soft" style="margin:0;font-size:12px;color:#434a55;
    line-height:1.6;">এই ইমেইলটি পাঠানো হয়েছে কারণ এই ঠিকানার জন্য
    শিক্ষকপ্লাস কোড চাওয়া হয়েছিল।</p>
  <p lang="en" class="sp-soft" style="margin:2px 0 0;font-size:12px;
    color:#434a55;line-height:1.6;">You received this because a
    ShikkhokPlus code was requested for this address.
    ShikkhokPlus by Nirmata.</p>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>
""")


def render_email_html(code: str) -> str:
    """Render the HTML part of an emailed code.

    :param code: The six-digit code
    :return: The HTML document
    """
    return EMAIL_HTML_TEMPLATE.substitute(
        code=html.escape(code), play_url=html.escape(PLAY_URL)
    )
