"""Bounded structured extraction only. No fetching, uploads, entity expansion or execution."""

import hashlib
import re
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

from app.schemas.references import PARSER_VERSION

ALLOWED_HOSTS = frozenset(
    {"ecfr.gov", "www.ecfr.gov", "govinfo.gov", "www.govinfo.gov", "fincen.gov", "www.fincen.gov"}
)
MAX_RAW = 1048576
MAX_EXTRACTED = 262144
MAX_CHUNK = 32768


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def approved_url(value):
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or parsed.fragment
            or "\\" in value
            or any(ord(c) < 33 for c in value)
            or any(p in (".", "..") for p in unquote(parsed.path).split("/"))
        ):
            raise ValueError
        return parsed.hostname
    except (ValueError, TypeError):
        raise ValueError("Unapproved publisher URL") from None


def normalize(parts):
    # Preserve paragraph boundaries and all non-active text, including exceptions/instructions.
    return "\n".join(line for line in (" ".join(p.split()) for p in parts) if line).strip()


class MainSections(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.main_depth = None
        self.main_seen = False
        self.skip = []
        self.sections = []
        self.parts = []
        self.key = "document-context"
        self.locator = "main"
        self.nodes = 0

    def flush(self):
        text = normalize(self.parts)
        if text:
            self.sections.append((self.key, self.locator, text))
        self.parts = []

    def handle_starttag(self, tag, attrs):
        self.nodes += 1
        if self.nodes > 10000:
            raise ValueError("HTML node limit")
        if tag not in {"br", "img", "hr", "meta", "input", "link", "source", "wbr"}:
            self.depth += 1
        if self.depth > 64:
            raise ValueError("HTML depth limit")
        if tag == "main":
            if self.main_seen:
                raise ValueError("Ambiguous main content")
            self.main_seen = True
            self.main_depth = self.depth
        if tag in {"script", "style", "iframe", "object", "template", "svg"}:
            self.skip.append(tag)
        if self.main_depth is not None and not self.skip:
            if tag == "h4":
                self.flush()
                self.key = "faq-" + str(len(self.sections))
                self.locator = "main/h4[" + str(len(self.sections)) + "]"
            props = dict(attrs)
            if tag == "div" and "usa-accordion__content" in props.get("class", ""):
                self.locator = "main/#" + props.get("id", self.key)

    def handle_endtag(self, tag):
        if self.skip and tag == self.skip[-1]:
            self.skip.pop()
        if (
            self.main_depth is not None
            and not self.skip
            and tag in {"p", "li", "h1", "h2", "h3", "h4", "div", "br"}
        ):
            self.parts.append("\n")
        if tag == "main" and self.main_depth is not None:
            self.flush()
            self.main_depth = None
        if tag not in {"br", "img", "hr", "meta", "input", "link", "source", "wbr"}:
            self.depth = max(0, self.depth - 1)

    def handle_data(self, data):
        if self.main_depth is not None and not self.skip:
            self.parts.append(data)

    def handle_decl(self, decl):
        if decl.lower().strip() != "doctype html":
            raise ValueError("Unsupported declaration")


def extract(raw, media_type):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_RAW or b"\x00" in raw:
        raise ValueError("Invalid text source size/type")
    text = raw.decode("utf-8-sig", errors="strict")
    if re.search(r"<!\s*(?:ENTITY|DOCTYPE(?!\s+html\s*>))", text, re.I):
        raise ValueError("Unsafe document declaration")
    if media_type == "application/xml":
        root = ElementTree.fromstring(text)
        if sum(1 for _ in root.iter()) > 10000:
            raise ValueError("XML node limit")

        def depth(node, n=0):
            if n > 64:
                raise ValueError("XML depth limit")
            for child in node:
                depth(child, n + 1)

        depth(root)
        sections = []
        for element in root.iter():
            if element.tag == "DIV8" and element.get("TYPE") == "SECTION":
                key = element.get("N", "")
                if not re.fullmatch(r"[0-9]{1,4}\.[0-9]{1,4}", key):
                    raise ValueError("Invalid section")
                sections.append((key, "DIV8[@N='" + key + "']", normalize(element.itertext())))
            elif element.tag == "SECTION" and element.get("id"):
                key = element.get("id")
                sections.append((key, "SECTION[@id='" + key + "']", normalize(element.itertext())))
    elif media_type == "text/html":
        parser = MainSections()
        parser.feed(text)
        parser.close()
        if parser.main_depth is not None or parser.skip:
            raise ValueError("Incomplete main content")
        sections = parser.sections
    elif media_type == "text/plain":
        sections = [("full-text", "utf8:full-text", text.strip())]
    else:
        raise ValueError("Unsupported source media")
    if not 1 <= len(sections) <= 100 or len({k for k, _, _ in sections}) != len(sections):
        raise ValueError("Missing or ambiguous complete sections")
    chunks = []
    document = bytearray()
    for key, locator, body in sections:
        data = body.encode()
        if not data or len(data) > MAX_CHUNK or len(key) > 120 or len(locator) > 240:
            raise ValueError("Section/locator exceeds bounds")
        if document:
            document.extend(b"\n\n")
        start = len(document)
        document.extend(data)
        chunks.append(
            {
                "section": key,
                "locator": locator,
                "start_byte": start,
                "end_byte": len(document),
                "body_text": body,
                "text_sha256": sha(data),
            }
        )
    if len(document) > MAX_EXTRACTED:
        raise ValueError("Extracted source limit")
    return {
        "parser_version": PARSER_VERSION,
        "raw_sha256": sha(raw),
        "extracted": document.decode(),
        "extracted_sha256": sha(bytes(document)),
        "chunks": chunks,
    }
