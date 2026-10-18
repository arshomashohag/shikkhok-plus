"""Response and error schemas, and the shared Money schema component.

A strict mypy island: ``strict = true`` with ``disallow_any_explicit``. An
``Any`` in a response model is a hole straight through the schema-wide
privacy assertion, because such a field carries a profile value at runtime
while declaring nothing in the generated document.
"""
