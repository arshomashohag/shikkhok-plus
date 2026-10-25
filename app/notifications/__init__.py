"""Push notification delivery, shared across every feature that sends.

**A package of its own rather than a module inside the feature that
happens to be its first caller** [OQ-4, NFR19.24]. D3 owns this adapter
and D4 consumes the same one; an adapter living in ``app/fees`` is one
D4 copies rather than imports, which produces exactly the outcome OQ-4
exists to prevent -- two adapters with two different ``UNREGISTERED``
behaviours, and a dead-token table that grows for ever on whichever side
got it wrong.

That is not a convention here. ``tests/notifications/test_boundary.py``
asserts that no module under a feature package defines an FCM client, in
the same shape as the money module's import gate, because absent a
mechanical check the failure mode is prevented only by D4's author
remembering.
"""
