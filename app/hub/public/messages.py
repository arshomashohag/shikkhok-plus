"""The public hub's own strings, in English and Bangla.

Public pages are rendered on the server, so their words live here rather
than in the Android or web bundles. Every key carries both locales; a
missing locale is a ``KeyError`` at the call, never a silent English
fallback on a Bangla page.

The vocabulary labels -- class levels, teaching modes, admissions,
curricula and weekdays -- are the apps' own words for the same values,
copied rather than shared because the server image carries no client
bundle. ``tests/hub/test_public_routes.py`` asserts each equals the
generated web bundle, so the two cannot drift apart.

Numbers the pages generate (counts, page numbers, fees) are written in
Latin digits in both locales, as the app bundles write them.
"""

from __future__ import annotations

from typing import Final, Literal

__all__ = ["LOCALES", "MESSAGES", "Locale", "t"]

#: The locales every public page is served in.
Locale = Literal["en", "bn"]

#: The same locales as a tuple, English (the ``x-default``) first.
LOCALES: Final[tuple[Locale, ...]] = ("en", "bn")

#: Each message key's text per locale. ``{name}``-style fields are filled
#: by :func:`t`.
MESSAGES: Final[dict[str, dict[Locale, str]]] = {
    # Named in place of a centre's teachers when none agreed to be named.
    "centre_faculty": {"en": "Centre faculty", "bn": "সেন্টারের শিক্ষকবৃন্দ"},
    # Page chrome.
    "site_name": {"en": "ShikkhokPlus", "bn": "শিক্ষকপ্লাস"},
    "hub_name": {"en": "ShikkhokPlus Hub", "bn": "শিক্ষকপ্লাস হাব"},
    "other_language": {"en": "বাংলা", "bn": "English"},
    "skip_to_content": {"en": "Skip to content", "bn": "মূল লেখায় যান"},
    "hub_label": {"en": "Hub", "bn": "হাব"},
    "nav_label": {"en": "Main", "bn": "প্রধান"},
    "nav_find": {"en": "Find a tutor", "bn": "শিক্ষক খুঁজুন"},
    "nav_about": {"en": "About ShikkhokPlus", "bn": "শিক্ষকপ্লাস সম্পর্কে"},
    "open_app": {"en": "Open the app", "bn": "অ্যাপ খুলুন"},
    "footer_label": {"en": "Footer", "bn": "ফুটার"},
    "footer_faq": {"en": "FAQ", "bn": "প্রশ্নোত্তর"},
    "footer_web_app": {"en": "Web app", "bn": "ওয়েব অ্যাপ"},
    "breadcrumb": {"en": "You are here", "bn": "আপনি এখানে"},
    # The landing page: what the hub is, before anything is searched.
    "search_lead": {
        "en": "Tutors and coaching centres who chose to list their batches. "
        "See the subjects, class times and, where shown, the fee, all in "
        "one place.",
        "bn": "যেসব শিক্ষক ও কোচিং সেন্টার নিজেরাই তাদের ব্যাচ তালিকাভুক্ত "
        "করেছেন। বিষয়, ক্লাসের সময় আর দেখানো থাকলে ফি, সব এক জায়গায়।",
    },
    "browse_by_class": {"en": "Browse by class:", "bn": "শ্রেণি অনুযায়ী দেখুন:"},
    "listed_heading": {
        "en": "Listed on ShikkhokPlus",
        "bn": "শিক্ষকপ্লাসে তালিকাভুক্ত",
    },
    "listed_sub": {
        "en": "Every tutor and centre here chose to be listed.",
        "bn": "এখানকার প্রত্যেক শিক্ষক ও সেন্টার নিজের ইচ্ছায় তালিকাভুক্ত হয়েছেন।",
    },
    "how_heading": {"en": "How it works", "bn": "যেভাবে কাজ করে"},
    "how_1_title": {
        "en": "Search by subject and area",
        "bn": "বিষয় ও এলাকা দিয়ে খুঁজুন",
    },
    "how_1_body": {
        "en": "Type a subject or a name, pick a class and your district, then "
        "narrow it to your area.",
        "bn": "একটি বিষয় বা নাম লিখুন, শ্রেণি ও জেলা বেছে নিন, তারপর আপনার এলাকা বেছে নিন।",
    },
    "how_2_title": {"en": "Compare batches", "bn": "ব্যাচ মিলিয়ে দেখুন"},
    "how_2_body": {
        "en": "See each batch's class times, how it is taught and whether "
        "admissions are open.",
        "bn": "প্রতিটি ব্যাচের ক্লাসের সময়, পড়ানোর ধরন আর ভর্তি খোলা আছে কি না দেখুন।",
    },
    "how_3_title": {"en": "Get to know the teacher", "bn": "শিক্ষককে জানুন"},
    "how_3_body": {
        "en": "Read about their qualifications and how they teach, and see "
        "their other batches.",
        "bn": "তাদের যোগ্যতা ও পড়ানোর ধরন জানুন, আর তাদের অন্য ব্যাচগুলোও দেখুন।",
    },
    "trust_1_title": {
        "en": "Listed only by choice",
        "bn": "শুধু নিজের ইচ্ছায় তালিকাভুক্ত",
    },
    "trust_1_body": {
        "en": "Nobody appears here until they publish their own page.",
        "bn": "নিজের পাতা প্রকাশ না করা পর্যন্ত কেউ এখানে দেখা যান না।",
    },
    "trust_2_title": {"en": "No child's details", "bn": "শিশুর কোনো তথ্য নয়"},
    "trust_2_body": {
        "en": "No student's name, photo, marks or attendance is ever shown.",
        "bn": "কোনো শিক্ষার্থীর নাম, ছবি, নম্বর বা হাজিরা কখনও দেখানো হয় না।",
    },
    "trust_3_title": {"en": "Straight from the app", "bn": "সরাসরি অ্যাপ থেকে"},
    "trust_3_body": {
        "en": "Class times come from the teacher's own ShikkhokPlus routine.",
        "bn": "ক্লাসের সময় আসে শিক্ষকের নিজের শিক্ষকপ্লাস রুটিন থেকে।",
    },
    "teach_title": {"en": "Do you teach batches?", "bn": "আপনি কি ব্যাচ পড়ান?"},
    "teach_body": {
        "en": "Publish your page from the ShikkhokPlus app and choose which "
        "batches to show, so families nearby can find you.",
        "bn": "শিক্ষকপ্লাস অ্যাপ থেকে আপনার পাতা প্রকাশ করুন আর কোন ব্যাচগুলো "
        "দেখাবেন বেছে নিন, যাতে কাছের পরিবারগুলো আপনাকে খুঁজে পায়।",
    },
    "teach_link": {
        "en": "List my batches",
        "bn": "আমার ব্যাচ তালিকাভুক্ত করুন",
    },
    # Cards and the two detail pages, as the hub design lays them out.
    "see_batches": {"en": "See batches", "bn": "ব্যাচগুলো দেখুন"},
    "per_month": {"en": "per month", "bn": "প্রতি মাসে"},
    "details_heading": {"en": "Details", "bn": "বিস্তারিত"},
    "where_heading": {"en": "When and where", "bn": "কখন ও কোথায়"},
    "batch_area": {"en": "Area", "bn": "এলাকা"},
    "owner_kind": {"en": "Listed as", "bn": "ধরন"},
    "batch_offered_by": {"en": "by {name}", "bn": "{name}-এর ব্যাচ"},
    "about_teacher": {"en": "About the teacher", "bn": "শিক্ষক পরিচিতি"},
    "about_organisation": {"en": "About the centre", "bn": "সেন্টার পরিচিতি"},
    "owner_page_link": {"en": "See {name}'s page", "bn": "{name}-এর পাতা দেখুন"},
    # Search.
    "search_title": {
        "en": "Find a tutor or coaching centre",
        "bn": "শিক্ষক বা কোচিং সেন্টার খুঁজুন",
    },
    "search_description": {
        "en": "Search tutors and coaching centres on ShikkhokPlus by subject, "
        "class and area.",
        "bn": "বিষয়, শ্রেণি ও এলাকা অনুযায়ী শিক্ষকপ্লাসে শিক্ষক ও কোচিং সেন্টার খুঁজুন।",
    },
    "search_label": {"en": "Subject, name or area", "bn": "বিষয়, নাম বা এলাকা"},
    "search_placeholder": {
        "en": "Physics, পদার্থবিজ্ঞান, Math…",
        "bn": "পদার্থবিজ্ঞান, গণিত, Physics…",
    },
    "search_button": {"en": "Search", "bn": "খুঁজুন"},
    "search_results": {"en": "{total} found", "bn": "{total}টি পাওয়া গেছে"},
    "search_none": {
        "en": "Nothing matched. Try fewer words.",
        "bn": "কিছু মেলেনি। কম শব্দ দিয়ে চেষ্টা করুন।",
    },
    "search_filtered": {
        "en": "Some filters are applied.",
        "bn": "কিছু ফিল্টার চালু আছে।",
    },
    "search_clear_filters": {"en": "Clear filters", "bn": "ফিল্টার মুছুন"},
    "search_district": {"en": "District", "bn": "জেলা"},
    "search_any_district": {"en": "All districts", "bn": "সব জেলা"},
    "search_area": {"en": "Area in the district", "bn": "জেলার ভেতরে এলাকা"},
    "search_any_area": {"en": "All areas", "bn": "সব এলাকা"},
    "search_level": {"en": "Class", "bn": "শ্রেণি"},
    "search_any_level": {"en": "Any class", "bn": "যেকোনো শ্রেণি"},
    "search_upazilas": {"en": "Upazilas", "bn": "উপজেলা"},
    "search_whole_city": {"en": "All of {name}", "bn": "{name}-এর সব এলাকা"},
    "page_previous": {"en": "Previous page", "bn": "আগের পাতা"},
    "page_next": {"en": "Next page", "bn": "পরের পাতা"},
    "page_of": {"en": "Page {page} of {pages}", "bn": "পাতা {page} / {pages}"},
    # Owner cards and pages.
    "kind_teacher": {"en": "Tutor", "bn": "শিক্ষক"},
    "kind_organisation": {"en": "Coaching centre", "bn": "কোচিং সেন্টার"},
    "runs_classes": {
        "en": "Runs classes on ShikkhokPlus",
        "bn": "শিক্ষকপ্লাসে ক্লাস চালান",
    },
    "owner_description": {
        "en": "{name} on ShikkhokPlus.",
        "bn": "শিক্ষকপ্লাসে {name}।",
    },
    "owner_about": {"en": "About", "bn": "পরিচিতি"},
    "owner_qualifications": {"en": "Qualifications", "bn": "যোগ্যতা"},
    "owner_teaching_mode": {"en": "How they teach", "bn": "পড়ানোর ধরন"},
    "owner_address": {"en": "Address", "bn": "ঠিকানা"},
    "owner_contact": {"en": "Contact", "bn": "যোগাযোগ"},
    "owner_batches": {"en": "Batches", "bn": "ব্যাচসমূহ"},
    "owner_no_batches": {
        "en": "No batches are listed yet.",
        "bn": "এখনও কোনো ব্যাচ তালিকাভুক্ত নয়।",
    },
    # Batch cards and pages.
    "batch_description": {
        "en": "{title} by {name} on ShikkhokPlus.",
        "bn": "শিক্ষকপ্লাসে {name}-এর {title}।",
    },
    "batch_untitled": {
        "en": "(No public title yet)",
        "bn": "(এখনও কোনো শিরোনাম নেই)",
    },
    "batch_subjects": {"en": "Subjects", "bn": "বিষয়"},
    "batch_levels": {"en": "Classes", "bn": "শ্রেণি"},
    "batch_curriculum": {"en": "Curriculum", "bn": "শিক্ষাক্রম"},
    "batch_mode": {"en": "How it is taught", "bn": "পড়ানোর ধরন"},
    "batch_admissions": {"en": "Admissions", "bn": "ভর্তি"},
    "batch_fee": {"en": "Monthly fee", "bn": "মাসিক ফি"},
    "batch_schedule": {"en": "Class times", "bn": "ক্লাসের সময়"},
    "batch_teachers": {"en": "Taught by", "bn": "যিনি পড়ান"},
    "batch_syllabus": {"en": "Syllabus", "bn": "সিলেবাস"},
    "batch_all_of_owner": {
        "en": "All batches of {name}",
        "bn": "{name}-এর সব ব্যাচ",
    },
    # Photos.
    "photos": {"en": "Photos", "bn": "ছবি"},
    "photo_awaiting_review": {
        "en": "Awaiting review",
        "bn": "পর্যালোচনার অপেক্ষায়",
    },
    # Reporting, preview, and the two fixed pages.
    "report_page": {"en": "Report this page", "bn": "এই পাতাটি রিপোর্ট করুন"},
    # Join requests [H5]. Shown only while join requests are switched on and
    # the owner accepts them; "join request" is ভর্তির অনুরোধ, as the apps say.
    "enquiry_link": {"en": "Ask to join", "bn": "ভর্তির অনুরোধ পাঠান"},
    "enquiry_link_batch": {
        "en": "Ask to join this class",
        "bn": "এই ক্লাসে ভর্তির অনুরোধ পাঠান",
    },
    "report_photo": {"en": "Report this photo", "bn": "এই ছবিটি রিপোর্ট করুন"},
    "preview_banner": {
        "en": "Preview — not public yet",
        "bn": "প্রিভিউ — এখনও প্রকাশিত নয়",
    },
    "not_found_title": {"en": "Page not found", "bn": "পাতাটি পাওয়া যায়নি"},
    "not_found_body": {
        "en": "This page is not on ShikkhokPlus, or is not public.",
        "bn": "এই পাতাটি শিক্ষকপ্লাসে নেই, অথবা প্রকাশিত নয়।",
    },
    "not_found_search": {"en": "Search the hub", "bn": "হাবে খুঁজুন"},
    "too_many_title": {"en": "Too many requests", "bn": "অনেক বেশি অনুরোধ"},
    "too_many_body": {
        "en": "Please wait a minute and try again.",
        "bn": "এক মিনিট অপেক্ষা করে আবার চেষ্টা করুন।",
    },
    # Reviews and ratings [H4]. Shown only while reviews are switched on.
    # Below the threshold every batch reads the same line, whatever its
    # count, so 0, 1 and 2 reviews cannot be told apart [F18, T9-a].
    "reviews_heading": {"en": "Reviews", "bn": "রিভিউ"},
    "reviews_count": {"en": "{count} reviews", "bn": "{count}টি রিভিউ"},
    "reviews_below_threshold": {
        "en": "Ratings appear once a class has 3 reviews.",
        "bn": "কোনো ক্লাসে 3টি রিভিউ হলে রেটিং দেখা যাবে।",
    },
    "reviews_most_recent": {
        "en": "Showing the {shown} most recent reviews.",
        "bn": "সাম্প্রতিকতম {shown}টি রিভিউ দেখানো হচ্ছে।",
    },
    "rating_out_of": {"en": "{average} out of 5", "bn": "5-এর মধ্যে {average}"},
    "rating_stars": {"en": "{stars} stars", "bn": "{stars} তারকা"},
    "reply_heading": {"en": "Reply from the teacher", "bn": "শিক্ষকের উত্তর"},
    "report_review": {"en": "Report this review", "bn": "এই রিভিউটি রিপোর্ট করুন"},
    "report_reply": {"en": "Report this reply", "bn": "এই উত্তরটি রিপোর্ট করুন"},
    "sort_label": {"en": "Sort by", "bn": "সাজানোর ক্রম"},
    "sort_relevance": {"en": "Best match", "bn": "সবচেয়ে মানানসই"},
    "sort_rating": {"en": "Rating", "bn": "রেটিং"},
    # Who wrote a review: a tenure bucket, never a name, an initial, a
    # class or a day. V1 reviewers are guardians only.
    "review_by_lt_6m": {
        "en": "Verified guardian · enrolled under 6 months",
        "bn": "যাচাইকৃত অভিভাবক · 6 মাসের কম সময় ধরে ভর্তি",
    },
    "review_by_6_12m": {
        "en": "Verified guardian · enrolled 6–12 months",  # noqa: RUF001 -- the decided copy's en dash
        "bn": "যাচাইকৃত অভিভাবক · 6–12 মাস ধরে ভর্তি",  # noqa: RUF001 -- the decided copy's en dash
    },
    "review_by_gt_1y": {
        "en": "Verified guardian · enrolled over 1 year",
        "bn": "যাচাইকৃত অভিভাবক · 1 বছরের বেশি সময় ধরে ভর্তি",
    },
    # A review's or reply's month: the name, then the year in Latin digits.
    "month_1": {"en": "Jan", "bn": "জানুয়ারি"},
    "month_2": {"en": "Feb", "bn": "ফেব্রুয়ারি"},
    "month_3": {"en": "Mar", "bn": "মার্চ"},
    "month_4": {"en": "Apr", "bn": "এপ্রিল"},
    "month_5": {"en": "May", "bn": "মে"},
    "month_6": {"en": "Jun", "bn": "জুন"},
    "month_7": {"en": "Jul", "bn": "জুলাই"},
    "month_8": {"en": "Aug", "bn": "আগস্ট"},
    "month_9": {"en": "Sep", "bn": "সেপ্টেম্বর"},
    "month_10": {"en": "Oct", "bn": "অক্টোবর"},
    "month_11": {"en": "Nov", "bn": "নভেম্বর"},
    "month_12": {"en": "Dec", "bn": "ডিসেম্বর"},
    # The apps' vocabulary labels, equal to the generated web bundle.
    "hub_level_class_1": {"en": "Class 1", "bn": "প্রথম শ্রেণি"},
    "hub_level_class_2": {"en": "Class 2", "bn": "দ্বিতীয় শ্রেণি"},
    "hub_level_class_3": {"en": "Class 3", "bn": "তৃতীয় শ্রেণি"},
    "hub_level_class_4": {"en": "Class 4", "bn": "চতুর্থ শ্রেণি"},
    "hub_level_class_5": {"en": "Class 5", "bn": "পঞ্চম শ্রেণি"},
    "hub_level_class_6": {"en": "Class 6", "bn": "ষষ্ঠ শ্রেণি"},
    "hub_level_class_7": {"en": "Class 7", "bn": "সপ্তম শ্রেণি"},
    "hub_level_class_8": {"en": "Class 8", "bn": "অষ্টম শ্রেণি"},
    "hub_level_class_9": {"en": "Class 9", "bn": "নবম শ্রেণি"},
    "hub_level_class_10": {"en": "Class 10", "bn": "দশম শ্রেণি"},
    "hub_level_class_11": {"en": "Class 11", "bn": "একাদশ শ্রেণি"},
    "hub_level_class_12": {"en": "Class 12", "bn": "দ্বাদশ শ্রেণি"},
    "hub_level_ssc": {"en": "SSC", "bn": "এসএসসি"},
    "hub_level_hsc": {"en": "HSC", "bn": "এইচএসসি"},
    "hub_level_admission": {"en": "Admission test", "bn": "ভর্তি পরীক্ষা"},
    "hub_level_o_level": {"en": "O Level", "bn": "ও লেভেল"},
    "hub_level_a_level": {"en": "A Level", "bn": "এ লেভেল"},
    "hub_level_other": {"en": "Other", "bn": "অন্যান্য"},
    "hub_mode_in_person": {"en": "In person", "bn": "সামনাসামনি"},
    "hub_mode_home_visit": {"en": "Home visits", "bn": "বাসায় গিয়ে"},
    "hub_mode_online": {"en": "Online", "bn": "অনলাইনে"},
    "hub_batch_admissions_open": {"en": "Open", "bn": "খোলা"},
    "hub_batch_admissions_waitlist": {"en": "Waitlist", "bn": "অপেক্ষমাণ তালিকা"},
    "hub_batch_admissions_closed": {"en": "Closed", "bn": "বন্ধ"},
    "hub_curriculum_national_bangla": {
        "en": "National curriculum (Bangla version)",
        "bn": "জাতীয় শিক্ষাক্রম (বাংলা ভার্সন)",
    },
    "hub_curriculum_national_english": {
        "en": "National curriculum (English version)",
        "bn": "জাতীয় শিক্ষাক্রম (ইংলিশ ভার্সন)",
    },
    "hub_curriculum_english_medium": {"en": "English medium", "bn": "ইংলিশ মিডিয়াম"},
    "hub_curriculum_madrasah": {"en": "Madrasah", "bn": "মাদ্রাসা"},
    "hub_curriculum_other": {"en": "Other", "bn": "অন্যান্য"},
    "weekday_mon": {"en": "Mon", "bn": "সোম"},
    "weekday_tue": {"en": "Tue", "bn": "মঙ্গল"},
    "weekday_wed": {"en": "Wed", "bn": "বুধ"},
    "weekday_thu": {"en": "Thu", "bn": "বৃহঃ"},
    "weekday_fri": {"en": "Fri", "bn": "শুক্র"},
    "weekday_sat": {"en": "Sat", "bn": "শনি"},
    "weekday_sun": {"en": "Sun", "bn": "রবি"},
}


def t(key: str, locale: Locale, **fields: object) -> str:
    """Look up one message in one locale, filling its fields.

    :param key: The message key
    :param locale: ``en`` or ``bn``
    :param fields: Values for the message's ``{name}`` fields
    :return: The text
    :raises KeyError: The key, its locale, or a field it names is missing
    """
    text = MESSAGES[key][locale]
    return text.format(**fields) if fields else text
