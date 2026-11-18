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
    # Reporting, preview, and the two fixed pages.
    "report_page": {"en": "Report this page", "bn": "এই পাতাটি রিপোর্ট করুন"},
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
