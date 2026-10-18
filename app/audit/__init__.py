"""The append-only authentication audit log.

The log holds no OTP, no token, no phone number and no child name. An
audit log that leaks what it audits is a common and self-defeating
mistake, so the correlation id -- and nothing else -- ties a row back to
the request that produced it [BR6.2].
"""
