#!/usr/bin/env python3
"""Product one-liner and pull-request URLs for a feature plan."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def outcome_sentence(markdown: str) -> str:
    """First sentence under a product.md Outcome heading."""
    collecting = False
    parts: list[str] = []
    for line in markdown.splitlines():
        if not collecting:
            if line.strip() == "## Outcome":
                collecting = True
            continue
        if not line.strip():
            if parts:
                break
            continue
        if line.startswith("#"):
            break
        parts.append(line.strip())
    paragraph = re.sub(r"\s+", " ", " ".join(parts)).strip()
    if not paragraph:
        return ""
    match = re.match(r"^(.+?\.)(?:\s|$)", paragraph)
    return match.group(1) if match else paragraph


_ISSUE_PREFIX = re.compile(r"^(?:SL|HC|C)-\d+\s+", re.IGNORECASE)
_COVER_PREFIX = re.compile(r"^Cover\s+", re.IGNORECASE)
_E2E_SUFFIX = re.compile(r"\s+in E2E$", re.IGNORECASE)


def prs_from_record(record: str) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    title = ""
    for line in record.splitlines():
        title_match = re.match(r"^-\s+Title:\s+(.+)$", line)
        url_match = re.match(r"^-\s+URL:\s+(https://\S+)\s*$", line)
        if title_match:
            title = title_match.group(1).strip()
        elif url_match:
            found.append({"title": title, "url": url_match.group(1)})
            title = ""
    return found


def pr_urls(record: str) -> list[str]:
    return [item["url"] for item in prs_from_record(record)]


def strip_pr_title(title: str) -> str:
    text = title.strip()
    text = _COVER_PREFIX.sub("", text)
    text = _ISSUE_PREFIX.sub("", text)
    text = _ISSUE_PREFIX.sub("", text)
    text = _E2E_SUFFIX.sub("", text)
    return text.strip().rstrip(".")


def short_pr_url(url: str) -> str:
    return re.sub(r"^https?://", "", url.strip())


def lead_from_titles(titles: list[str]) -> str:
    for title in titles:
        text = strip_pr_title(title)
        if text:
            return text if text.endswith(":") else f"{text}:"
    return ""


def lead_from_product(markdown: str) -> str:
    for line in markdown.splitlines():
        match = re.match(
            r"^#\s+(?:(?:SL|HC|C)-\d+\s+)?(?:Product:\s*)?(.+)$",
            line.strip(),
            re.IGNORECASE,
        )
        if not match:
            continue
        text = match.group(1).strip().rstrip(".")
        if not text or text.lower() == "product":
            continue
        text = text[0].upper() + text[1:]
        return text if text.endswith(":") else f"{text}:"
    sentence = outcome_sentence(markdown).rstrip(".")
    if not sentence:
        return ""
    return f"{sentence}:"


def format_message(prs: list[dict[str, str]], product: str = "") -> str:
    titles = [item.get("title", "") for item in prs]
    lead = lead_from_titles(titles) or lead_from_product(product)
    lines = [lead] if lead else []
    for item in prs:
        url = short_pr_url(item.get("url", ""))
        if url:
            lines.append(f"• {url}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sentence = sub.add_parser("sentence")
    sentence.add_argument("--product", required=True)
    urls = sub.add_parser("urls")
    urls.add_argument("--record", required=True)
    message = sub.add_parser("message")
    message.add_argument("--product", default="")
    message.add_argument("--record", default="")
    args = parser.parse_args()
    if args.command == "sentence":
        text = outcome_sentence(Path(args.product).read_text(encoding="utf-8"))
        if text:
            print(text)
        return 0
    if args.command == "urls":
        for url in pr_urls(Path(args.record).read_text(encoding="utf-8")):
            print(url)
        return 0
    product = Path(args.product).read_text(encoding="utf-8") if args.product else ""
    if args.record:
        prs = prs_from_record(Path(args.record).read_text(encoding="utf-8"))
    else:
        prs = []
        for line in sys.stdin:
            if "\t" not in line:
                continue
            title, url = line.rstrip("\n").split("\t", 1)
            if not url.strip():
                continue
            prs.append({"title": title.strip(), "url": url.strip()})
    text = format_message(prs, product)
    if text:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
