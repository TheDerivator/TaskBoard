"""Post rendering: Markdown features, mentions and task links, and sanitizing (XSS vectors)."""

import re

import pytest

from taskboard.services.markdown import attachment_ids_in, render_markdown

ATTACHMENT = "api/attachments/" + "a" * 32 + "/map.png"


def test_markdown_features_from_the_design() -> None:
    html = render_markdown(
        "**Week 38 status**\n\n- Defect maps pulled\n- Cluster on **4 Sep**\n\n`WR-2291`"
    )
    assert "<strong>Week 38 status</strong>" in html
    assert "<li>Defect maps pulled</li>" in html
    assert "<code>WR-2291</code>" in html


def test_single_newlines_become_line_breaks() -> None:
    assert "first<br>" in render_markdown("first\nsecond")


def test_mentions_and_task_keys() -> None:
    html = render_markdown("@Anna can we show it? It supports T-117 and t-999 (not a key).")
    assert '<span class="mention">@Anna</span>' in html
    assert '<a class="task-ref" href="t/117" rel="noopener noreferrer">T-117</a>' in html
    assert "t-999" in html and 'href="t/999"' not in html


def test_mentions_with_dots_and_accents_but_not_emails() -> None:
    html = render_markdown("@chloé.martens, mail anna@example.com")
    assert '<span class="mention">@chloé.martens</span>' in html
    assert "anna@example.com" in html and "@example" not in html.replace("anna@example.com", "")


def test_no_decoration_inside_code_or_links() -> None:
    html = render_markdown("`@Anna T-117` and [T-104 @x](https://example.com)")
    assert "mention" not in html and "task-ref" not in html


def test_tables_and_strikethrough() -> None:
    html = render_markdown("| a | b |\n|:--|--:|\n| 1 | 2 |\n\n~~gone~~")
    assert "<table>" in html and "<s>gone</s>" in html
    assert 'style="text-align:left"' in html


def test_images_only_from_our_attachments() -> None:
    ours = render_markdown(f"![defect map]({ATTACHMENT})")
    assert f'<img src="{ATTACHMENT}" alt="defect map">' in ours
    theirs = render_markdown("![pixel](https://tracker.example.com/p.gif)")
    assert "tracker.example.com" not in theirs


@pytest.mark.parametrize(
    "attack",
    [
        "<script>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
        "[click](javascript:alert(1))",
        "[click](data:text/html;base64,PHNjcmlwdD4=)",
        '<a href="https://x" onclick="alert(1)">x</a>',
        "<iframe src='https://evil'></iframe>",
        "![x](javascript:alert(1))",
        '<svg onload="alert(1)">',
    ],
)
def test_xss_vectors_are_neutralized(attack: str) -> None:
    """Attacks may survive as harmless escaped text, but never as markup."""
    html = render_markdown(attack)
    tags = re.findall(r"<[^>]*>", html)
    for tag in tags:
        lowered = tag.lower()
        assert not re.match(r"<(script|iframe|svg|object|embed|style)", lowered), html
        assert not re.search(r"\son\w+\s*=", lowered), html
        assert "javascript:" not in lowered and "data:" not in lowered, html


def test_external_links_are_safe() -> None:
    html = render_markdown("[docs](https://example.com/a?b=1)")
    assert '<a href="https://example.com/a?b=1" rel="noopener noreferrer">docs</a>' in html


def test_attachment_ids_referenced_by_a_body() -> None:
    body = f"see ![a]({ATTACHMENT}) and api/attachments/{'b' * 32}/x.jpg, not api/attachments/zzz"
    assert attachment_ids_in(body) == {"a" * 32, "b" * 32}
