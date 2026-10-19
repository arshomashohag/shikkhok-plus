"""HTTP endpoints.

This Unit opens four routes: three auth routes and the health check.
Every other Unit's routes resolve a lens; these do not, which is why
each one is named in an explicit allowlist rather than discovered.
"""
