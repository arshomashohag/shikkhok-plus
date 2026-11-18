"""The image sanitiser's placeholder: what Terraform creates the function with.

Terraform cannot build the real package (Pillow for arm64), and a saved plan
applied on another runner would not find a zip built during the plan. So the
function is created from this, committed as image-sanitiser.zip, and the
deploy workflow uploads the real package (`make lambda-image`) after the
infrastructure job and before the release. Terraform ignores the code from
then on (lambda.tf).

It fails rather than succeeding quietly, so an upload arriving in the gap
is a logged, failed invocation (the function is not retried, lambda.tf)
rather than an apparent success. That upload gets no result.json, and the
API's `complete` settles it as unreadable after 20 minutes [R7c].
"""


def handler(event: object, context: object) -> None:
    """Refuse every event until the real package is deployed."""
    raise RuntimeError("image sanitiser not deployed yet: run the deploy workflow")
