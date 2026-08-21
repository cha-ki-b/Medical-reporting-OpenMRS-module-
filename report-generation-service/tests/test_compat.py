"""
Interpreter-compatibility guards.

The service declares Python 3.11+ (README §3). CI and the Docker image run 3.12, so a
construct that is valid only on 3.12 passes every local check and then fails at *import* on a
3.11 host - taking the whole service down rather than degrading one feature.

That is not hypothetical. `layout_html.py` once carried a backslash inside an f-string
expression, which PEP 701 legalised in 3.12 but which is a SyntaxError on 3.11. On a 3.11
sandbox the entire suite collapsed to "40 errors, 2 failures" purely because that one module
could not be parsed.

Detecting it is fiddlier than it looks, and two obvious approaches do not work:

* `ast.parse(..., feature_version=(3, 11))` does not reject it. PEP 701 changed the
  *tokenizer*, and `feature_version` only constrains grammar-level features.
* Scanning `tokenize` output does not either - on 3.12 an f-string is no longer a single
  STRING token, so the offending inner quotes arrive as separate plain STRING tokens and the
  scan sees nothing.

What does work is reading the f-string's raw source segment back out of the AST and scanning
that. Because the detector is subtle, `test_the_detector_actually_catches_the_real_regression`
runs it against the exact line that caused the outage, so a detector that silently stops
working fails the build instead of going quiet.
"""

from __future__ import annotations

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parent.parent / "app"

MIN_PYTHON = (3, 11)

# The literal line that broke the service, kept verbatim as a regression fixture.
KNOWN_BAD_SOURCE = (
    "def render(f):\n"
    "    return f'<td{\" class=\\\"em\\\"\" if f.emphasis else \"\"}>x</td>'\n"
)

KNOWN_GOOD_SOURCE = (
    "def render(f):\n"
    "    attr = ' class=\"em\"' if f.emphasis else ''\n"
    '    return f"<td{attr}>x</td>"\n'
)


def find_backslash_in_fstring_expressions(source: str, label: str = "<source>") -> list[str]:
    """
    Return a location for every f-string whose *expression* part contains a backslash.

    Works by recovering each f-string's original source text from the AST and walking it with
    a brace-depth counter, so it is independent of how the running interpreter tokenises
    f-strings.
    """
    offenders: list[str] = []
    tree = ast.parse(source, filename=label)

    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        segment = ast.get_source_segment(source, node)
        if not segment:
            continue

        depth = 0
        index = 0
        while index < len(segment):
            char = segment[index]
            if char == "{":
                # `{{` is an escaped literal brace, not the start of an expression.
                if index + 1 < len(segment) and segment[index + 1] == "{":
                    index += 2
                    continue
                depth += 1
            elif char == "}":
                depth = max(0, depth - 1)
            elif char == "\\" and depth > 0:
                offenders.append(f"{label}:{node.lineno}")
                break
            index += 1

    return offenders


def _source_files() -> list[pathlib.Path]:
    files = sorted(APP.rglob("*.py"))
    assert files, "no application sources were found"
    return files


def test_the_detector_actually_catches_the_real_regression():
    """
    Self-check. Without this the suite could report a clean bill of health simply because the
    detector had stopped detecting - which is exactly what happened to a `tokenize`-based
    version of it on Python 3.12.
    """
    assert find_backslash_in_fstring_expressions(KNOWN_BAD_SOURCE, "bad.py"), (
        "the detector no longer recognises the construct that caused the original outage"
    )
    assert not find_backslash_in_fstring_expressions(KNOWN_GOOD_SOURCE, "good.py"), (
        "the detector flags the corrected form, so it would fail the build on good code"
    )


def test_no_application_module_has_a_backslash_in_an_fstring_expression():
    offenders: list[str] = []
    for path in _source_files():
        offenders += find_backslash_in_fstring_expressions(
            path.read_text(encoding="utf-8"), path.name
        )

    assert not offenders, (
        "a backslash inside an f-string expression is a SyntaxError on Python "
        f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]}; assign the value to a variable first. "
        f"Offenders: {offenders}"
    )


def test_every_module_parses_under_the_minimum_supported_python():
    """
    Catches grammar-level features newer than the floor we advertise (match statements, PEP
    695 generics, and so on). It does *not* catch the f-string case above - hence the separate
    detector.
    """
    for path in _source_files():
        source = path.read_text(encoding="utf-8")
        try:
            ast.parse(source, filename=str(path), feature_version=MIN_PYTHON)
        except SyntaxError as error:  # pragma: no cover - only on a real regression
            raise AssertionError(
                f"{path.name} does not parse under Python "
                f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]}: {error}"
            ) from error


def test_the_emphasis_attribute_still_renders():
    """The rewrite of the offending line must keep its behaviour."""
    from app.layout_html import HtmlLayout
    from app.schemas import DocField

    assert HtmlLayout._emphasis_attr(DocField(label="x", emphasis=True)) == ' class="em"'
    assert HtmlLayout._emphasis_attr(DocField(label="x", emphasis=False)) == ""
