"""Batches, enrollment seats, and the teacher's roster.

The Unit that brings the first second party into the system. Every query
here scopes on a value carried **inside** a lens object rather than on a
parameter, so a handler cannot compile a teacher-facing query without
having resolved one.
"""
