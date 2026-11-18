"""The image sanitiser's placeholder: what Terraform creates the function with.

Terraform cannot build the real package (Pillow for arm64), and a saved plan
applied on another runner would not find a zip built during the plan. So the
function is created from this, committed as image-sanitiser.zip, and the
deploy workflow uploads the real package (`make lambda-image`) after the
infrastructure job and before the release. Terraform ignores the code from
then on (lambda.tf).

It fails rather than succeeding quietly: an upload arriving in the gap is
then retried by Lambda, by when the real code is normally in place, instead
of being accepted with no result.json ever written.
"""


def handler(event: object, context: object) -> None:
    """Refuse every event until the real package is deployed."""
    raise RuntimeError("image sanitiser not deployed yet: run the deploy workflow")
