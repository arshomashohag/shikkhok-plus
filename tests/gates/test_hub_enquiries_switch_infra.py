"""The join-requests switch reaches the container, defaulting off.

The switch is read from SSM by the release, written into the runtime
env and forwarded by compose. Terraform creates the parameter ``off``
and never touches its value again, so an apply cannot flip it. The
release's own reading of it lives in ``test_deploy_workflow.py``, beside
the record-step harness it needs.
"""

from __future__ import annotations

import pathlib
import re

from tests.gates._hub_switches import (
    DEPLOY,
    compose_forwards,
    parameter_block,
    released_path,
    runbook,
    steps,
    switch_paths,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEPLOY_ROLE = ROOT / "infra" / "bootstrap" / "deploy_role.tf"
SWITCH = "SHIKKHOKPLUS_HUB_ENQUIRIES"
RESOURCE = "hub_enquiries"
RUNBOOK = "Switching join requests on"

#: The amended first sentence of ``project.md``'s Forbidden rule that the
#: owner adopts before the switch is turned on (Task 10's brief). The
#: runbook quotes it, so the person amending the rule copies this text and
#: not a paraphrase of it.
AMENDED_RULE = (
    "NEVER expose anything a student or guardian writes to any teacher, "
    "except a hub review its author explicitly submitted for public "
    "display, and a join request a guardian explicitly sent to that owner, "
    "which only that owner's managers see, never with the guardian's "
    "contact unless they chose to share it on that request."
)


def _flat(text: str) -> str:
    """Collapse a Markdown passage's line breaks and quote markers.

    :param text: Text as wrapped in ``infra/README.md``
    :return: The same words on one line, single-spaced
    """
    return " ".join(text.replace("> ", " ").split())


def test_ssm_switch_parameter_defaults_off_and_ignores_value() -> None:
    body = parameter_block(RESOURCE)

    assert re.search(
        r'name\s*=\s*"/shikkhokplus/\$\{var\.name_prefix\}/hub-enquiries"', body
    )
    assert re.search(r'type\s*=\s*"String"', body)
    assert re.search(r'value\s*=\s*"off"', body)
    assert re.search(r"ignore_changes\s*=\s*\[value\]", body)


def test_deploy_role_may_read_the_enquiries_switch() -> None:
    granted = re.search(
        r'Sid\s*=\s*"PublicUrl".*?Resource\s*=\s*\[(.*?)\]\s*:',
        DEPLOY_ROLE.read_text(),
        re.S,
    )
    assert granted is not None
    assert '"hub-enquiries"' in granted.group(1)


def test_both_compose_files_forward_switch_defaulting_off() -> None:
    for name, values in compose_forwards(SWITCH).items():
        assert values, f"{name} does not forward {SWITCH}"
        assert set(values) == {"${SHIKKHOKPLUS_HUB_ENQUIRIES:-off}"}


# ---------------------------------------------------------------------------
# The "Switching join requests on" runbook. Task 1 writes the parameter
# table and the deploy-role paragraph; Task 10 adds the human checks that
# come before the flip: the owner's amendment of the project.md rule that
# forbids join requests as worded, then the D6 declarations. The table and
# the commands must name the parameter Terraform actually creates, or a
# person following them writes a parameter nothing reads.
# ---------------------------------------------------------------------------


def test_switch_paths_are_the_ones_the_release_reads() -> None:
    paths = switch_paths(RESOURCE)
    assert re.search(r"\$\(ses_param hub-enquiries\)", DEPLOY.read_text())

    assert paths == {
        "staging": "/shikkhokplus/shikkhokplus-staging/hub-enquiries",
        "production": "/shikkhokplus/shikkhokplus-production/hub-enquiries",
    }
    for environment, path in paths.items():
        assert released_path("hub-enquiries", environment) == path


def test_runbook_tables_the_parameter_terraform_creates() -> None:
    section = runbook(RUNBOOK)

    for environment, path in switch_paths(RESOURCE).items():
        assert f"| {environment} | `{path}` |" in section
    assert "test_hub_enquiries_switch_infra.py" in section


def test_runbook_says_the_deploy_role_must_read_it() -> None:
    section = runbook(RUNBOOK)

    assert "**The deploy role must be able to read it.**" in section
    assert "Cannot read the hub join requests switch" in section
    assert "bootstrap/deploy_role.tf" in section


def test_runbook_names_the_message_the_release_stops_with() -> None:
    # The runbook tells a person what to do when the release stops; the
    # sentence it quotes must be the one the release prints.
    quoted = re.search(
        r'"(Cannot read the hub join requests switch)"', runbook(RUNBOOK)
    )
    assert quoted is not None
    assert f"::error::{quoted.group(1)}" in DEPLOY.read_text()


def test_runbook_lists_rule_amendment_and_d6_before_flip() -> None:
    section = runbook(RUNBOOK)
    numbered = steps(section)

    def first(pattern: str) -> int:
        for index, step in enumerate(numbered):
            if re.search(pattern, step):
                return index
        raise AssertionError(f"no runbook step matches {pattern!r}")

    amend = first(r"project\.md")
    d6 = first(r"\bD6\b")
    flip = first(r"aws ssm put-parameter")
    deploy = first(r"(?i)dispatch a deploy")
    check = first(r"(?i)Ask to join")
    assert len(numbered) == 5
    assert [amend, d6, flip, deploy, check] == [0, 1, 2, 3, 4]

    # Step 1 is the owner's, through the learnings ritual, with the
    # brief's wording verbatim; the runbook states it and edits nothing.
    assert "learnings ritual" in _flat(numbered[amend])
    assert AMENDED_RULE in _flat(numbered[amend])
    # Step 2 names all three declarations the switch makes true.
    for declaration in ("Data Safety", "Families", "PRIVACY.md"):
        assert declaration in numbered[d6]
    # Step 5 proves both halves: the link, and a request reaching the
    # owner's inbox.
    assert re.search(r"(?i)inbox", numbered[check])

    commands = re.findall(r"aws ssm put-parameter[^\n`]*", section)
    paths = switch_paths(RESOURCE)
    named = {
        re.search(r"--name (\S+)", command).group(1)  # type: ignore[union-attr]
        for command in commands
    }
    assert named == set(paths.values()), "a put-parameter names another path"
    for command in commands:
        assert "--overwrite" in command
        assert "--type String" in command
        assert re.search(r"--value (on|off)\b", command)
    for path in paths.values():
        assert re.search(rf"--name {re.escape(path)} .*--value on\b", section)
    # Staging is written before production, in the same step.
    staging = section.index(paths["staging"] + " --type String --value on")
    production = section.index(paths["production"] + " --type String --value on")
    assert staging < production

    # Switching off is the same command with `off`, and it never strands a
    # guardian's request: they can still read and withdraw it, and the
    # 90-day purge still runs.
    assert re.search(r"(?i)switch(ing)? off.*`off`", section, re.S)
    flat = _flat(section)
    assert "withdraw" in flat and "90 days" in flat
    # The stub's "not written here yet" warning goes once the checks are.
    assert "not written here yet" not in section


def test_runbook_says_infra_must_be_applied_first() -> None:
    # The parameter exists only once infra/ has been applied with H5's
    # change; writing `on` to a name that does not exist yet creates a
    # parameter outside Terraform's state.
    flat = _flat(runbook(RUNBOOK))

    assert "apply `infra/`" in flat


def test_runbook_names_the_data_safety_item_that_exists() -> None:
    # Step 2 sends the person to an item of docs/legal/README.md; that item
    # must exist and answer the form's questions (what is collected,
    # shared with whom, never, deleted), and the Families note must carry
    # the adult-guardian declaration.
    step = _flat(steps(runbook(RUNBOOK))[1])
    item = re.search(r"`docs/legal/README\.md` item (\d+) \(\"(.*?)\"\)", step)
    assert item is not None
    legal = (ROOT / "docs" / "legal" / "README.md").read_text()
    body = re.search(
        rf"^\*\*{item.group(1)}\. {re.escape(item.group(2))} \[H5\]\.\*\*(.*?)"
        r"(?=^\*\*)",
        legal,
        re.S | re.M,
    )
    assert body is not None, "the runbook names an item the README lacks"
    for answer in ("What is collected", "Shared with whom", "Never", "Deleted"):
        assert f"- **{answer}.**" in body.group(1)
    assert "90 days after it was sent" in _flat(body.group(1))
    families = _flat(legal.split("**Families target-audience declaration.**")[1])
    assert "parent or guardian aged 18 or older" in families
    assert "no message reaches a child account from a teacher" in families


def test_site_qualifies_what_a_teacher_cannot_see() -> None:
    # Runbook step 2 says the site needs no change because every sentence
    # telling a reader that a teacher cannot see what a guardian writes
    # already carries the join-request exception, in both languages.
    pages = ROOT / "site" / "src" / "pages"
    claims = {
        pages / "index.html": (
            "writes about themselves is shown to any teacher",
            "A teacher can never see what a student or guardian writes",
        ),
        pages / "faq" / "index.html": ("or anything a student or guardian writes",),
        pages / "bn" / "index.html": (
            "তা কোনো শিক্ষককে দেখানো হয় না",
            "কোনো শিক্ষক তা কখনো দেখতে পারেন না",
        ),
        pages / "bn" / "faq" / "index.html": ("নিজের সম্পর্কে যা লেখেন",),
    }
    exception = {"en": "where join requests are offered", "bn": "ভর্তির অনুরোধ চালু আছে"}
    for page, sentences in claims.items():
        language = "bn" if "bn" in page.parts else "en"
        paragraphs = re.findall(r"<p>(.*?)</p>", page.read_text(), re.S)
        for sentence in sentences:
            holding = [p for p in paragraphs if sentence in p]
            assert holding, f"{page.name}: {sentence!r} not found"
            for paragraph in holding:
                assert exception[language] in paragraph.lower(), (
                    f"{page.relative_to(ROOT)} says {sentence!r} unqualified"
                )
    assert "release the site first" not in runbook(RUNBOOK)
