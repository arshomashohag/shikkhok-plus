# Contract Design Questions — Unique usernames

## Question 1: How does the sign-in request carry the single field? (OQ4)

A. A new optional `login` field on the existing `PasswordSignInRequest`; exactly one of `login`, `phone` or `email` must be present, so installed clients keep sending `phone` or `email` unchanged
B. A new request type on a new route
X. Other (please specify)

[Answer]: A

## Question 2: Where does `username_required` appear?

A. On `MeResponse` only, next to `has_password`, because both clients already route the signed-in person from `GET /v1/me`; the three token-issuing responses stay unchanged
B. On `MeResponse` and on every token-issuing response
X. Other (please specify)

[Answer]: A

## Question 3: How are contact replace and remove expressed?

A. Replace reuses the existing add flow: `POST /v1/me/contact` gains an optional `password`, required when the account already holds a contact of that kind, and the verify step swaps the old one out. Remove is a new `POST /v1/me/contact/remove` with the kind and the password
B. New dedicated replace and remove routes, leaving the add flow untouched
X. Other (please specify)

[Answer]: A

## Question 4: What is the versioning and breaking-change policy?

A. The existing one: `/v1` stays additive, new fields are optional on requests and may be added to responses, clients ignore unknown fields, and the committed `openapi.json` with its schema-diff gate is the contract of record
B. A new `/v2` for the identity routes
X. Other (please specify)

[Answer]: A

## Question 5: What error behaviour do the new routes follow?

A. The existing envelope (`code`, server-set `retryable`, `message_key`), with new `account.username.*` and `account.contact.*` keys added to `message-keys.json` and to both clients' string bundles in the same change
B. Free-text error messages for the new routes
X. Other (please specify)

[Answer]: A
