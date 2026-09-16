import importlib
import itertools
import re
import string
from itertools import count

import mistune
import mistune.helpers
import mistune.inline_parser
import mistune.list_parser
from mistune.plugins.table import table as table_plugin

from notifications_utils import MAGIC_SEQUENCE, magic_sequence_regex
from notifications_utils.formatters import create_sanitised_html_for_url, replace_svg_dashes, unescape_strict
from notifications_utils.qr_code import (
    QR_CODE_MAX_BYTES,
    QrCodeTooLong,
    paragraph_is_qr_code_markup_regex,
    qr_code_as_svg,
    qr_code_placeholder,
)

LINK_STYLE = "word-wrap: break-word; color: #1D70B8;"

# Escape a bare `&` (not already the start of a real entity like `&amp;`/`&#40;`) plus
# `<`/`>`. Quotes are left alone - they only matter inside attribute values, which are
# handled separately (e.g. via safe_url) - and pre-existing entities are left verbatim
# rather than being decoded and re-escaped.
_BARE_AMPERSAND = re.compile(r"&(?!#[0-9]{1,7};|#[xX][0-9a-fA-F]+;|[^\t\n\f <&#;]{1,32};)")


def _escape_text(text):
    text = _BARE_AMPERSAND.sub("&amp;", text)
    return text.replace("<", "&lt;").replace(">", "&gt;")


# Letter/email markdown uses `^` (not `>`) to mark a block quote / inset text.
_BLOCK_QUOTE_LEADING_PATTERN = re.compile(r"^ *\^ ?", flags=re.M)
_BLOCK_QUOTE_RULE = re.compile(r"^( *\^[^\n]+(\n[^\n]+)*\n*)+", flags=re.M)

# Bullets are `•`/`*`/`-` (never `+`) and ordered markers are `1.` (never `1)`).
# The space after the marker is optional (`1.one` is as valid as `1. one`).
_LIST_PATTERN = r"^(?P<list_1> {0,3})(?P<list_2>[•*-]|\d{1,9}\.)(?P<list_3>[ \t]*.*)$"

# Bare `https://...` URLs get auto-linked; matches mistune's own `url` plugin pattern
# but keeps the original (pre-mistune-3) trailing-punctuation exclusion set.
_URL_PATTERN = r"""https?:\/\/[^\s<]+[^<.,:"')\]\s]"""


# mistune.list_parser has no public hook for either of these two behaviours, so - in
# the same spirit as the old mistune-0.8.4 grammar monkey-patches this replaces - patch
# its private helpers: 1) a bullet character doesn't need a following space (`1.one` is
# as valid as `1. one`), and 2) `•` is a real bullet, not silently treated as `-`.
def _get_list_bullet(c):
    if c == ".":
        return r"\d{0,9}\."
    if c == "•":
        return "•"
    if c == "*":
        return r"\*"
    return "-"


def _compile_list_item_pattern(bullet, leading_width):
    if leading_width > 3:
        leading_width = 3
    return (
        r"^(?P<listitem_1> {0," + str(leading_width) + "})"
        r"(?P<listitem_2>" + bullet + ")"
        r"(?P<listitem_3>[ \t]*.*)$"
    )


mistune.list_parser._get_list_bullet = _get_list_bullet
mistune.list_parser._compile_list_item_pattern = _compile_list_item_pattern


# A nested block (e.g. a sub-list) only needs to be indented as far as the marker
# itself (e.g. 2 columns for "3."), not marker-plus-following-space (3 columns for
# "3. ") as mistune computes by default - matching the old, more lenient nesting rule.
def _compile_continue_width(text, leading_width):
    text = mistune.list_parser._expand_leading_tabs(text, leading_width)
    m2 = mistune.list_parser._LINE_HAS_TEXT.match(text)
    if m2:
        indent = mistune.list_parser._count_indent(text)
        space_width = 1 if indent >= 5 else indent
        text = text[space_width:] + "\n"
    else:
        space_width = 1
        text = ""
    return text, leading_width


mistune.list_parser._compile_continue_width = _compile_continue_width


# Personalisation placeholders get substituted into content as a literal `<span
# class='placeholder'>...</span>` tag (with spaces and HTML-entity-encoded brackets
# inside) before markdown ever sees it - including, sometimes, inside a `[text](url)`
# link's url. mistune 3's non-angle-bracket href scanning stops at the first raw
# whitespace, and always HTML-unescapes + percent-encodes whatever it captures. Neither
# suits a url that's actually an embedded HTML tag: this tolerates whitespace while
# inside a `<...>` tag, and (matching the old mistune-0.8.4 behaviour this content model
# relies on) passes such hrefs through completely verbatim rather than transforming them.
def _next_href_char_action(c, level, in_tag, block):
    """Classify one href character: ("invalid"|"stop"|"consume", new_level, new_in_tag)."""
    if c == "\x00":
        return "invalid", level, in_tag
    if c in mistune.helpers.ASCII_WHITESPACE and not in_tag:
        return "stop", level, in_tag

    if c == "<":
        in_tag = True
    elif c == ">":
        in_tag = False

    if not block:
        if c == "(":
            level += 1
        elif c == ")":
            if level == 0:
                return "stop", level, in_tag
            level -= 1

    return "consume", level, in_tag


def _parse_link_href(src, start_pos, block=False):
    pos = mistune.helpers._skip_link_start_whitespace(src, start_pos)
    if pos >= len(src):
        return None, None

    # Note: unlike stock mistune, a leading `<` is NOT treated as CommonMark's
    # angle-bracket href syntax and delegated to `_parse_angle_link_href` - that
    # scanner stops at the first unescaped `>`, which breaks as soon as the href
    # itself contains embedded HTML (e.g. a personalisation placeholder's
    # `<span class='placeholder'>...</span>`, substituted in before markdown ever
    # parses this content - see the comment on `_next_href_char_action` above).
    # Every href, angle-prefixed or not, goes through that same tolerant loop.
    if block and src[pos] in mistune.helpers.ASCII_WHITESPACE:
        return None, None

    start = pos
    level = 0
    in_tag = False
    while pos < len(src):
        if src[pos] == "\\":
            pos = min(pos + 2, len(src))
            continue

        action, level, in_tag = _next_href_char_action(src[pos], level, in_tag, block)
        if action == "invalid":
            return None, None
        if action == "stop":
            break
        pos += 1

    if not block and level != 0:
        return None, None
    if pos == start:
        return None, None
    return src[start:pos], pos


def _parse_link(src, pos):
    href, href_pos = mistune.helpers.parse_link_href(src, pos)
    if href is None:
        return None, None
    title, title_pos = mistune.helpers.parse_link_title(src, href_pos, len(src))
    next_pos = title_pos or href_pos
    next_pos = mistune.helpers._skip_ascii_whitespace(src, next_pos)
    if next_pos >= len(src) or src[next_pos] != ")":
        return None, None

    if "<" in href:
        attrs = {"url": href}
    else:
        href = mistune.helpers.unescape_char(href)
        attrs = {"url": mistune.helpers.escape_url(href)}
    if title:
        attrs["title"] = title
    return attrs, next_pos + 1


mistune.helpers.parse_link_href = _parse_link_href
mistune.inline_parser.parse_link = _parse_link


# mistune 3's core render pipeline strips leading/trailing ASCII whitespace -
# including plain spaces - off every block's text before inline-parsing it
# (`text.strip(" \r\n\t\f")`). The newline/tab/form-feed part matters (it's what
# keeps block-splitting artefacts like a paragraph's trailing "\n" from turning
# into a spurious extra `<br>` under hard-wrap), but stripping plain spaces is a
# new-in-mistune-3 side effect mistune 0.8.4 never had, and this content model
# doesn't want: e.g. `_find_and_sanitise_urls` in notifynl-api can strip a
# leading url entirely, leaving a genuine leading space; letter/email QR code
# data can rely on an exact trailing space. Strip the same characters mistune 3
# does, minus the plain space, so structural whitespace is still normalised but
# meaningful leading/trailing spaces inside content survive.
def _iter_render_preserving_block_text_spaces(self, tokens, state):
    for tok in tokens:
        if "children" in tok:
            children = self._iter_render(tok["children"], state)
            tok["children"] = list(children)
        elif "text" in tok:
            text = tok.pop("text")
            tok["children"] = self.inline(text.strip("\r\n\t\f"), state.env)
        yield tok


# `mistune`'s own __init__.py rebinds the `markdown` attribute on the `mistune`
# package to a convenience function, shadowing the `mistune.markdown` submodule -
# so plain attribute access (`mistune.markdown`, even via `import mistune.markdown
# as x`) resolves to that function, not the submodule, once `mistune` is fully
# imported. Go via `importlib` to reach the real submodule/class regardless.
importlib.import_module("mistune.markdown").Markdown._iter_render = _iter_render_preserving_block_text_spaces


def _parse_url_link(inline, m, state):
    text = m.group(0)
    pos = m.end()
    if state.in_link:
        inline.process_text(text, state)
        return pos
    state.append_token({"type": "autolink", "raw": text, "attrs": {"is_email": False}})
    return pos


_DEFAULT_RULES_WITH_PLUS_BULLET = list(mistune.BlockParser.DEFAULT_RULES)
_DEFAULT_RULES_WITH_PLUS_BULLET.insert(_DEFAULT_RULES_WITH_PLUS_BULLET.index("list"), "plus_bullet")


class NotifyBlockParser(mistune.BlockParser):
    SPECIFICATION = {
        **mistune.BlockParser.SPECIFICATION,
        "block_quote": r"^ {0,3}\^[^\n]*$",
        "list": _LIST_PATTERN,
        # the space after the leading #s is optional (`#heading` is as valid as `# heading`)
        "atx_heading": r"^ {0,3}(?P<atx_1>#{1,6})(?!#+)(?P<atx_2>[ \t]*.*?)$",
        # `+` looks like a bullet but is deliberately not one - each `+`-led line still
        # forces its own paragraph break, rather than merging into surrounding text
        "plus_bullet": r"^ {0,3}\+.*$",
    }
    DEFAULT_RULES = tuple(_DEFAULT_RULES_WITH_PLUS_BULLET)

    def parse_plus_bullet(self, m, state):
        end_pos = state.find_line_end()
        state.append_token({"type": "paragraph", "text": state.get_text(end_pos)})
        return end_pos

    def parse_block_quote(self, m, state):
        """Block quote / inset text, introduced by a leading `^` rather than `>`."""
        m2 = _BLOCK_QUOTE_RULE.match(state.src, state.cursor)
        text = _BLOCK_QUOTE_LEADING_PATTERN.sub("", m2.group(0))

        child = state.child_state(text)
        if state.depth() >= self.max_nested_level - 1:
            rules = [rule for rule in self.block_quote_rules if rule not in ("block_quote", "list")]
        else:
            rules = self.block_quote_rules
        self.parse(child, rules)

        state.append_token({"type": "block_quote", "children": child.tokens})
        return m2.end()


class NotifyInlineParser(mistune.InlineParser):
    # Letters/emails don't support emphasis, strong emphasis or inline code -
    # `*`/`_`/`` ` `` are left as literal characters. Strikethrough is a mistune
    # plugin we never enable, so `~~text~~` is already left alone.
    DEFAULT_RULES = tuple(rule for rule in mistune.InlineParser.DEFAULT_RULES if rule not in ("emphasis", "codespan"))

    # mistune 0.8.4's escape rule excluded `<` from its escapable-character set
    # (while including `>` and everything else) - an accidental quirk, but one
    # that's already baked into real, previously-delivered notification content
    # and every existing test expectation: a backslash-escaped `\<` falls through
    # to plain text (rendered as a literal `\` followed by an HTML-escaped `<`)
    # rather than being cleanly unescaped like `\>` and other punctuation is.
    # Reproduced here so this CVE-driven mistune bump doesn't silently change
    # already-rendered content for this one character.
    SPECIFICATION = {
        **mistune.InlineParser.SPECIFICATION,
        "escape": r"(?:\\[" + re.escape(string.punctuation.replace("<", "")) + "])+",
    }

    def __init__(self, hard_wrap=False):
        super().__init__(hard_wrap=hard_wrap)
        self.register("url_link", _URL_PATTERN, _parse_url_link, before="auto_link")

    def parse_auto_link(self, m, state):
        text = m.group(0)[1:-1]
        pos = m.end()
        if state.in_link:
            self.process_text(m.group(0), state)
            return pos
        state.append_token({"type": "autolink", "raw": text, "attrs": {"is_email": False}})
        return pos

    def parse_auto_email(self, m, state):
        text = m.group(0)[1:-1]
        pos = m.end()
        if state.in_link:
            self.process_text(m.group(0), state)
            return pos
        state.append_token({"type": "autolink", "raw": text, "attrs": {"is_email": True}})
        return pos


def qr_code_contents_from_paragraph(text):
    if match := paragraph_is_qr_code_markup_regex.fullmatch(text):
        return match[1]


class NotifyLetterMarkdownPreviewRenderer(mistune.HTMLRenderer):
    def __init__(self):
        super().__init__(escape=False)

    def _render_qr_data(self, data):
        if "<span class='placeholder" in data or '<span class="placeholder' in data:
            placeholder = qr_code_placeholder(data)
            return replace_svg_dashes(placeholder)
        data = unescape_strict(data)
        qr_data = qr_code_as_svg(data)
        return f"<div class='qrcode'>{replace_svg_dashes(qr_data)}</div>"

    def text(self, text):
        return _escape_text(text)

    def block_code(self, code, info=None):
        return code.rstrip("\n")

    def block_quote(self, text):
        return text

    def heading(self, text, level, **attrs):
        if level == 1:
            return super().heading(text, 2)
        return self.paragraph(text)

    def thematic_break(self):
        return '<div class="page-break">&nbsp;</div>'

    def paragraph(self, text):
        if not text.strip():
            return ""

        if qr_code_contents := qr_code_contents_from_paragraph(text):
            # Restore http:// or https:// and strip out the <strong> tag that gets injected by
            # the `link`/`autolink` methods
            text = self._render_qr_data(
                re.sub(r"<strong data-original-protocol='(https?://|)'>(.*?)</strong>", r"\1\2", qr_code_contents)
            )

        return f"<p>{text}</p>"

    def table(self, text):
        return ""

    def table_head(self, text):
        return ""

    def table_body(self, text):
        return ""

    def table_row(self, text):
        return ""

    def table_cell(self, text, align=None, head=False):
        return ""

    def autolink(self, text, is_email=False):
        proto_matcher = re.compile(r"^(https?://)")

        protocol = ""
        if match := proto_matcher.match(text):
            protocol = match.group(1)
            text = proto_matcher.sub("", text, 1)

        return f"<strong data-original-protocol='{protocol}'>{text}</strong>"

    def image(self, text, url, title=None):
        return ""

    def linebreak(self):
        return "<br>"

    def list_item(self, text):
        return f"<li>{text.strip()}</li>\n"

    def link(self, text, url, title=None):
        if url.startswith("span class='placeholder") and url.endswith("</span"):
            url = f"<{url}>"

        if title:
            return f'[{text}]({url} "{title}")'

        return f"[{text}]({url})"


class NotifyLetterMarkdownValidatingRenderer(NotifyLetterMarkdownPreviewRenderer):
    """Renders letter markdown as normal, except validates QR code data does not exceed a maximum length."""

    def _render_qr_data(self, data):
        if (num_bytes := len(data.encode("utf8"))) > QR_CODE_MAX_BYTES:
            raise QrCodeTooLong(num_bytes=num_bytes, data=data)

        return data


class NotifyEmailMarkdownRenderer(NotifyLetterMarkdownPreviewRenderer):
    def heading(self, text, level, **attrs):
        if level == 1:
            return (
                '<h2 style="Margin: 0 0 15px 0; padding: 10px 0 0 0; '
                'font-size: 27px; line-height: 35px; font-weight: bold; color: #0B0C0C;">'
                f"{text}"
                "</h2>"
            )
        if level == 2:
            return (
                '<h3 style="Margin: 0 0 15px 0; padding: 10px 0 0 0; '
                'font-size: 19px; line-height: 25px; font-weight: bold; color: #0B0C0C;">'
                f"{text}"
                "</h3>"
            )
        return self.paragraph(text)

    def thematic_break(self):
        return '<hr style="border: 0; height: 1px; background: #B1B4B6; Margin: 30px 0 30px 0;">'

    def linebreak(self):
        return "<br>"

    def list(self, text, ordered, **attrs):
        return (
            (
                '<table role="presentation" style="padding: 0 0 20px 0;">'
                "<tr>"
                '<td style="font-family: Helvetica, Arial, sans-serif;">'
                '<ol style="Margin: 0 0 0 20px; padding: 0; list-style-type: decimal;">'
                f"{text}"
                "</ol>"
                "</td>"
                "</tr>"
                "</table>"
            )
            if ordered
            else (
                '<table role="presentation" style="padding: 0 0 20px 0;">'
                "<tr>"
                '<td style="font-family: Helvetica, Arial, sans-serif;">'
                '<ul style="Margin: 0 0 0 20px; padding: 0; list-style-type: disc;">'
                f"{text}"
                "</ul>"
                "</td>"
                "</tr>"
                "</table>"
            )
        )

    def list_item(self, text):
        return (
            '<li style="Margin: 5px 0 5px; padding: 0 0 0 5px; font-size: 19px;'
            'line-height: 25px; color: #0B0C0C;">'
            f"{text.strip()}"
            "</li>"
        )

    def paragraph(self, text):
        if text.strip():
            return f'<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">{text}</p>'
        return ""

    def block_quote(self, text):
        return (
            '<div style="Margin: 0 0 20px 0;">'
            "<blockquote "
            'style="Margin: 0; border-left: 10px solid #B1B4B6;'
            'padding: 15px 0 0.1px 15px; font-size: 19px; line-height: 25px;"'
            ">"
            f"{text}"
            "</blockquote>"
            "</div>"
        )

    def link(self, text, url, title=None):
        if url.startswith("span class='placeholder") and url.endswith("</span"):
            url = f"<{url}>"

        if title:
            return create_sanitised_html_for_url(url, style=LINK_STYLE, title=title, link_text=text)
        return create_sanitised_html_for_url(url, style=LINK_STYLE, link_text=text)

    def autolink(self, text, is_email=False):
        if is_email:
            return text
        return create_sanitised_html_for_url(text, style=LINK_STYLE)


class NotifyPlainTextEmailMarkdownRenderer(NotifyEmailMarkdownRenderer):
    COLUMN_WIDTH = 65

    def heading(self, text, level, **attrs):
        if level == 1:
            return "".join(
                (
                    self.linebreak() * 3,
                    text,
                    self.linebreak(),
                    "=" * self.COLUMN_WIDTH,
                )
            )
        elif level == 2:
            return "".join(
                (
                    self.linebreak() * 3,
                    text,
                    self.linebreak(),
                    "-" * self.COLUMN_WIDTH,
                )
            )
        return self.paragraph(text)

    def thematic_break(self):
        pattern = "=-"
        pattern_iterator = itertools.cycle(pattern)
        return self.paragraph("".join(next(pattern_iterator) for _ in range(self.COLUMN_WIDTH)))

    def linebreak(self):
        return "\n"

    def list(self, text, ordered, **attrs):
        def _get_list_marker():
            decimal = count(1)
            return lambda _: f"{next(decimal)}." if ordered else "•"

        return "".join(
            (
                self.linebreak(),
                re.sub(
                    magic_sequence_regex,
                    _get_list_marker(),
                    text,
                ),
            )
        )

    def list_item(self, text):
        return "".join(
            (
                self.linebreak(),
                MAGIC_SEQUENCE,
                " ",
                text.strip(),
            )
        )

    def paragraph(self, text):
        if text.strip():
            return "".join(
                (
                    self.linebreak() * 2,
                    text,
                )
            )
        return ""

    def block_quote(self, text):
        return text

    def link(self, text, url, title=None):
        return "".join(
            (
                text,
                f" ({title})" if title else "",
                ": ",
                url,
            )
        )

    def autolink(self, text, is_email=False):
        return text


class NotifyEmailPreheaderMarkdownRenderer(NotifyPlainTextEmailMarkdownRenderer):
    def heading(self, text, level, **attrs):
        return self.paragraph(text)

    def thematic_break(self):
        return ""

    def link(self, text, url, title=None):
        return "".join(
            (
                text,
                f" ({title})" if title else "",
            )
        )


def _make_markdown(renderer):
    return mistune.Markdown(
        renderer=renderer,
        block=NotifyBlockParser(),
        inline=NotifyInlineParser(hard_wrap=True),
        plugins=[table_plugin],
    )


notify_email_markdown = _make_markdown(NotifyEmailMarkdownRenderer())
notify_plain_text_email_markdown = _make_markdown(NotifyPlainTextEmailMarkdownRenderer())
notify_email_preheader_markdown = _make_markdown(NotifyEmailPreheaderMarkdownRenderer())
notify_letter_preview_markdown = _make_markdown(NotifyLetterMarkdownPreviewRenderer())
notify_letter_qrcode_validator = _make_markdown(NotifyLetterMarkdownValidatingRenderer())
