"""Frontmatter parsing — single source of truth.

Every script that reads `summaries/<slug>.md` (or `projects/<name>.md`, or
`notes/<id>.md`) needs to extract the YAML-ish frontmatter block at the top.
Until now each script reinvented its own parser, with the weaker ones
(rename_pdfs, check_schemas, build_themes_bundle, build_tiers_bundle)
silently ignoring block-scalar fields like `why_cited: |` and the regex
variant in enrich_authors requiring strict Unix newlines.

This module owns the one good parser. Every script imports from here.

Supports:
  - scalar fields:                 `author: Smith, J.`
  - quoted scalars:                `title: "Some title"`
  - inline lists:                  `projects: [prelims, fnirs]`
  - literal block scalars:         `why_cited: |` + indented lines
  - folded block scalars:          `note: >` + indented lines
  - inline `# comments` after `|`/`>` markers
  - comment lines starting with `#`

Returns (fields_dict, body_text).
"""

from __future__ import annotations

import re


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Tiny YAML-ish frontmatter parser. Returns (fields, body)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_block = text[3:end].strip("\n")
    body = text[end + 4:].lstrip("\n")
    fields: dict = {}
    lines = fm_block.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if ":" not in line or line.lstrip().startswith("#"):
            i += 1
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip()
        # Block-list-of-flow-mappings — the YAML shape used by
        # `authors_detailed`:
        #   authors_detailed:
        #     - {family: Smith, given: "Jane R.", institution: "Stanford"}
        #     - {family: Jones, given: "A.", institution: ""}
        # When the value is empty and the next indented line(s) start with
        # `- {...}` we collect them into a list of dicts.
        if v == "" and i + 1 < len(lines):
            nxt = lines[i + 1]
            if nxt.lstrip().startswith("- {"):
                items: list[dict] = []
                i += 1
                while i < len(lines):
                    bl = lines[i]
                    stripped = bl.lstrip()
                    if bl.strip() == "":
                        i += 1
                        continue
                    if not stripped.startswith("- {"):
                        break
                    # Extract the {...} body and split into key/value pairs.
                    # Respects quoted strings (commas inside quotes don't split).
                    # If the closing brace isn't on this line (malformed /
                    # multi-line flow mapping), skip this item rather than crash.
                    if "}" not in stripped:
                        i += 1
                        continue
                    body_str = stripped[stripped.index("{") + 1 : stripped.rindex("}")]
                    item: dict = {}
                    j, n = 0, len(body_str)
                    while j < n:
                        # skip leading whitespace + comma
                        while j < n and body_str[j] in " ,":
                            j += 1
                        # read key up to ':'
                        kk = j
                        while kk < n and body_str[kk] != ":":
                            kk += 1
                        if kk >= n:
                            break
                        ik = body_str[j:kk].strip()
                        j = kk + 1
                        while j < n and body_str[j] == " ":
                            j += 1
                        # quoted value?
                        if j < n and body_str[j] == '"':
                            jj = j + 1
                            while jj < n and body_str[jj] != '"':
                                if body_str[jj] == "\\" and jj + 1 < n:
                                    jj += 2
                                    continue
                                jj += 1
                            iv = body_str[j + 1 : jj]
                            j = jj + 1
                        elif j < n and body_str[j] == "[":
                            # Nested flow-list value: `institutions: ["A", "B"]`.
                            # Scan to the matching `]`, respecting quoted
                            # strings (so a `,` inside `"A, B"` doesn't
                            # confuse the top-level comma-split at the outer
                            # flow-map level).
                            jj = j + 1
                            in_str = False
                            while jj < n:
                                c = body_str[jj]
                                if in_str:
                                    if c == "\\" and jj + 1 < n:
                                        jj += 2
                                        continue
                                    if c == '"':
                                        in_str = False
                                elif c == '"':
                                    in_str = True
                                elif c == "]":
                                    break
                                jj += 1
                            raw_list = body_str[j + 1 : jj]
                            j = jj + 1
                            # Split the list body on top-level commas
                            # (respecting quoted strings), then trim + unquote
                            # each element. Unquoted tokens like `unknown`
                            # come through as bare strings.
                            elems: list[str] = []
                            m, mm = 0, len(raw_list)
                            while m < mm:
                                while m < mm and raw_list[m] in " ,":
                                    m += 1
                                if m >= mm:
                                    break
                                if raw_list[m] == '"':
                                    e = m + 1
                                    while e < mm and raw_list[e] != '"':
                                        if raw_list[e] == "\\" and e + 1 < mm:
                                            e += 2
                                            continue
                                        e += 1
                                    elems.append(raw_list[m + 1 : e])
                                    m = e + 1
                                else:
                                    e = m
                                    while e < mm and raw_list[e] != ",":
                                        e += 1
                                    elems.append(raw_list[m:e].strip())
                                    m = e
                            iv = elems
                        else:
                            jj = j
                            while jj < n and body_str[jj] != ",":
                                jj += 1
                            iv = body_str[j:jj].strip()
                            # Strip optional quotes if any leaked through
                            if (iv.startswith('"') and iv.endswith('"')) or (iv.startswith("'") and iv.endswith("'")):
                                iv = iv[1:-1]
                            j = jj
                        if ik:
                            item[ik] = iv
                    items.append(item)
                    i += 1
                fields[k] = items
                continue
        if v.startswith("|") or v.startswith(">"):
            chevron = v[0]
            # Block scalar — collect subsequent indented lines until we hit
            # a less-indented (or empty-then-less-indented) line.
            block_lines: list[str] = []
            i += 1
            while i < len(lines):
                bl = lines[i]
                if bl.strip() == "":
                    block_lines.append("")
                    i += 1
                    continue
                if not bl.startswith((" ", "\t")):
                    break
                block_lines.append(bl.lstrip())
                i += 1
            joined = "\n".join(block_lines).strip("\n")
            if chevron == ">":
                # Fold single newlines within paragraphs into spaces.
                paragraphs = re.split(r"\n\s*\n", joined)
                joined = "\n\n".join(
                    re.sub(r"\s*\n\s*", " ", p) for p in paragraphs
                )
            fields[k] = joined
            continue
        # Strip surrounding quotes
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        # Inline list: [a, b, c]
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            fields[k] = (
                [x.strip() for x in inner.split(",") if x.strip()]
                if inner else []
            )
        else:
            fields[k] = v
        i += 1
    return fields, body


def split_frontmatter_text(text: str) -> tuple[str, str]:
    """Split a summary MD into (frontmatter_block_with_dashes, body).

    Used by rewriters that want to surgically edit the frontmatter without
    re-serialising it. Returns ("", text) if no frontmatter is detected.
    """
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end == -1:
        return "", text
    return text[: end + 4], text[end + 4:]
