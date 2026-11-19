"""Hub join requests: a guardian asks a teacher or centre to take a student.

Everything here is gated on the server-side join-requests switch
(:mod:`app.hub.enquiries.switch`), which is off by default. The switch
never gates a deletion.
"""
