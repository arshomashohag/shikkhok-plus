"""The public hub's photos: upload sessions, the owner's library, the bucket.

``storage`` is the only module that talks to S3; ``uploads`` signs uploads
under the quotas in ``quota`` and completes them from the sanitiser's
result; ``library`` lists, edits, reorders and withdraws; ``objects`` is the
bucket's deletion outbox and ``commands`` its cron entry point.
"""
