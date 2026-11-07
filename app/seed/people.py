"""Names, syllabi and phrasing the seeded history is written in.

Plain data, kept apart from the simulation so the scenario reads as
behaviour rather than as lists. The names are common Bangladeshi given
names and surnames in the Latin spelling teachers type into the app;
the syllabi follow the SSC (classes 9-10) General Math and Physics
textbooks in chapter order, so a week's weekly test covers topics a
real batch would have reached by then.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "ANNOUNCEMENTS",
    "FAMILY_NAMES",
    "FEMALE_NAMES",
    "GUARDIAN_GIVEN_NAMES",
    "MALE_NAMES",
    "SESSION_NOTES",
    "SYLLABUS",
]

MALE_NAMES: Final = (
    "Arif", "Tanvir", "Rafi", "Sakib", "Nafis", "Imran", "Fahim", "Rakib",
    "Shihab", "Tahmid", "Ayan", "Nayeem", "Rifat", "Sabbir", "Mahin",
    "Zarif", "Asif", "Tamim", "Sami", "Adnan", "Mehedi", "Rayhan", "Junaid",
    "Ishraq", "Farhan", "Labib", "Rashed", "Siam",
)  # fmt: skip

FEMALE_NAMES: Final = (
    "Nusrat", "Tasnim", "Anika", "Sadia", "Raisa", "Maliha", "Lamia",
    "Farzana", "Jannat", "Sumaiya", "Tahsin", "Mim", "Nabila", "Afia",
    "Samiha", "Ritu", "Prova", "Fariha", "Zerin", "Tanha", "Orin", "Ishita",
    "Mahira", "Nowshin", "Sanjida", "Rubaiya",
)  # fmt: skip

FAMILY_NAMES: Final = (
    "Hossain", "Rahman", "Islam", "Ahmed", "Chowdhury", "Khan", "Uddin",
    "Sarkar", "Das", "Roy", "Akter", "Haque", "Karim", "Mia", "Talukder",
    "Biswas", "Saha", "Sheikh", "Mollah", "Bhuiyan", "Siddique", "Alam",
)  # fmt: skip

GUARDIAN_GIVEN_NAMES: Final = (
    "Abdul", "Mohammad", "Jahangir", "Shahidul", "Nazrul", "Rezaul",
    "Shirin", "Rokeya", "Nasima", "Dilruba", "Kamrul", "Mizanur",
)  # fmt: skip

#: Each subject's topics in textbook order. A held class takes the next
#: one; the weekly test covers what the week took.
SYLLABUS: Final[dict[str, tuple[str, ...]]] = {
    "Math": (
        "Real numbers: classification and properties",
        "Real numbers: recurring decimals",
        "Sets: Venn diagrams and set operations",
        "Functions: domain and range",
        "Algebraic expressions: formulae and expansion",
        "Algebraic expressions: factorisation",
        "Algebraic expressions: remainder theorem",
        "Indices: laws of indices",
        "Logarithms: laws and change of base",
        "Equations in one variable: linear",
        "Equations in one variable: quadratic by factorisation",
        "Quadratic equations: completing the square",
        "Lines, angles and triangles: theorems",
        "Practical geometry: constructing triangles",
        "Parallelograms: properties and theorems",
        "Area of triangles and quadrilaterals",
        "Circles: chords and arcs",
        "Ratio and proportion: continued proportion",
        "Simultaneous linear equations: substitution",
        "Simultaneous linear equations: elimination and graphs",
        "Finite series: arithmetic progressions",
        "Finite series: geometric progressions",
        "Trigonometric ratios: definitions and identities",
        "Trigonometric ratios: standard angles",
        "Heights and distances",
        "Mensuration: surface area of solids",
        "Mensuration: volume of solids",
        "Statistics: mean, median and mode",
        "Statistics: frequency polygons and ogives",
        "Revision: algebra",
        "Revision: geometry",
        "Revision: trigonometry",
        "Revision: mensuration and statistics",
        "Model test review",
    ),
    "Physics": (
        "Physical quantities and measurement: units and dimensions",
        "Measurement: vernier scale and screw gauge",
        "Motion: rest, motion and scalar and vector quantities",
        "Motion: equations of motion",
        "Motion: free fall and graphs",
        "Force: Newton's laws of motion",
        "Force: momentum and its conservation",
        "Force: friction",
        "Work, power and energy: work-energy theorem",
        "Work, power and energy: conservation of energy",
        "Work, power and energy: efficiency",
        "State of matter and pressure: density",
        "Pressure: Pascal's law and hydraulic press",
        "Pressure: Archimedes' principle",
        "Effect of heat on matter: expansion",
        "Heat: specific heat and latent heat",
        "Waves and sound: wave characteristics",
        "Sound: echo and its uses",
        "Reflection of light: laws and plane mirrors",
        "Reflection of light: spherical mirrors",
        "Refraction of light: laws and refractive index",
        "Refraction: total internal reflection",
        "Lenses: image formation",
        "Static electricity: charge and induction",
        "Current electricity: Ohm's law",
        "Current electricity: series and parallel circuits",
        "Magnetic effect of current",
        "Revision: mechanics",
        "Revision: heat and waves",
        "Revision: light and electricity",
        "Model test review",
    ),
}

#: Notes a teacher adds to some classes.
SESSION_NOTES: Final = (
    "Homework: exercise questions 1 to 10.",
    "Several students were confused; will revise next class.",
    "Gave a short quiz at the end.",
    "Solved board questions from previous years.",
    "Class started 10 minutes late due to rain.",
    "Homework: creative questions from the textbook.",
    "Students should bring geometry boxes next class.",
)

#: Notices, keyed by when in the history they are posted. ``{batch}``,
#: ``{due_day}`` and ``{date}`` are filled at posting.
ANNOUNCEMENTS: Final[dict[str, str]] = {
    "welcome": (
        "Welcome to {batch}! Classes follow the routine in the app. "
        "Weekly tests are every Thursday on that week's topics."
    ),
    "fee_due": (
        "Reminder: this month's fee is due by the {due_day}th. You can pay "
        "by bKash or Nagad from the app, or in cash in class."
    ),
    "holiday": (
        "No classes on {date} for the Durga Puja holiday. Classes resume "
        "the next scheduled day."
    ),
    "model_test": (
        "Model test on {date}. The model test fee has been added in the app. "
        "Syllabus: everything covered so far."
    ),
    "extra_class": (
        "An extra revision class is scheduled on {date}. Attendance is "
        "strongly encouraged."
    ),
    "results": (
        "Weekly test results are published. Guardians can see the marks in the app."
    ),
}
