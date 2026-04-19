"""Static summaries of Apex classes and triggers using ANTLR4 parse trees + XPath."""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from typing import Any

from antlr4 import CommonTokenStream
from antlr4.error.ErrorListener import ErrorListener
from antlr4.tree.Tree import ParseTree
from antlr4.ParserRuleContext import ParserRuleContext
from antlr4.xpath.XPath import XPath

from app.services.salesforce.apex_parser import CaseInsensitiveInputStream
from app.services.salesforce.apex_parser.ApexLexer import ApexLexer
from app.services.salesforce.apex_parser.ApexParser import ApexParser

MD_NS = {"md": "http://soap.sforce.com/2006/04/metadata"}


class _SilentErrorListener(ErrorListener):
    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        return


def _original_text(source: str, ctx: ParserRuleContext) -> str:
    """Slice original source using parser positions (length matches lowercased lexer stream)."""
    if ctx.start is None or ctx.stop is None:
        return ctx.getText()
    return source[ctx.start.start : ctx.stop.stop + 1]


def _parse_tree(source: str, rule: str) -> tuple[ApexParser, ParseTree]:
    lexer = ApexLexer(CaseInsensitiveInputStream(source))
    stream = CommonTokenStream(lexer)
    parser = ApexParser(stream)
    parser.removeErrorListeners()
    parser.addErrorListener(_SilentErrorListener())
    if rule == "trigger":
        tree = parser.triggerUnit()
    else:
        tree = parser.compilationUnit()
    return parser, tree


def _api_version_from_meta(meta_xml: bytes | None) -> str | None:
    if not meta_xml:
        return None
    root = ET.fromstring(meta_xml)
    v = root.find("md:apiVersion", MD_NS)
    if v is not None and v.text:
        return v.text.strip()
    return None


def _soql_objects(soql_text: str) -> list[str]:
    out: list[str] = []
    m = re.search(r"\bfrom\s+([a-zA-Z0-9_]+)\b", soql_text, re.IGNORECASE)
    if m:
        out.append(m.group(1))
    return out


def _dml_objects_from_snippets(snippets: list[str]) -> list[str]:
    objs: set[str] = set()
    for sn in snippets:
        m = re.search(r"(insert|update|delete|undelete|upsert)\s*([a-zA-Z0-9_]+)", sn, re.IGNORECASE)
        if m:
            objs.add(m.group(2))
    return sorted(objs)


def _collect_dml_soql(
    parser: ApexParser, tree: ParseTree, source: str
) -> tuple[list[str], list[str]]:
    dml_snippets: list[str] = []
    for xp in (
        "//insertStatement",
        "//updateStatement",
        "//deleteStatement",
        "//upsertStatement",
        "//undeleteStatement",
    ):
        for ctx in XPath.findAll(tree, xp, parser):
            dml_snippets.append(_original_text(source, ctx))
    soql_literals = [
        _original_text(source, ctx) for ctx in XPath.findAll(tree, "//soqlLiteral", parser)
    ]
    return dml_snippets, soql_literals


def analyze_apex_class(source: str, meta_xml: bytes | None = None) -> dict[str, Any]:
    parser, tree = _parse_tree(source, "class")
    dml_snippets, soql_literals = _collect_dml_soql(parser, tree, source)

    methods: list[dict[str, Any]] = []
    for md in XPath.findAll(tree, "//methodDeclaration", parser):
        name = _original_text(source, md.id_()) if md.id_() else None
        ret = _original_text(source, md.typeRef()) if md.typeRef() else "void"
        params = (
            _original_text(source, md.formalParameters()) if md.formalParameters() else "()"
        )
        methods.append(
            {
                "name": name,
                "return_type": ret,
                "parameters": params,
                "annotations": [],
                "has_dml": bool(dml_snippets),
                "has_soql": bool(soql_literals),
                "has_callout": bool(
                    re.search(r"\bHttpRequest\b|\bHttp\.send\b", source)
                    or re.search(r"@future\s*\([^)]*callout\s*=\s*true", source, re.IGNORECASE)
                ),
            }
        )

    callout_detected = any(m["has_callout"] for m in methods) or bool(
        re.search(r"\bHttpRequest\b|\bHttp\.send\b", source)
        or re.search(r"@future\s*\([^)]*callout\s*=\s*true", source, re.IGNORECASE)
    )
    for m in methods:
        m["has_callout"] = callout_detected

    soql_objs: list[str] = []
    for lit in soql_literals:
        soql_objs.extend(_soql_objects(lit))

    return {
        "source_body": source,
        "methods": methods,
        "class_annotations": [],
        "dml_objects": _dml_objects_from_snippets(dml_snippets),
        "soql_objects": sorted(set(soql_objs)),
        "callout_detected": callout_detected,
        "api_version": _api_version_from_meta(meta_xml),
        "line_count": source.count("\n") + 1,
        "raw_xml_hash": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "parse_error": parser.getNumberOfSyntaxErrors() > 0,
    }


def analyze_apex_trigger(source: str, meta_xml: bytes | None = None) -> dict[str, Any]:
    parser, tree = _parse_tree(source, "trigger")
    dml_snippets, soql_literals = _collect_dml_soql(parser, tree, source)
    m = re.search(r"trigger\s+\w+\s+on\s+([a-zA-Z0-9_]+)\s*\(([^)]+)\)", source, re.IGNORECASE)
    trigger_object = m.group(1) if m else None
    trigger_events = [p.strip() for p in m.group(2).split(",")] if m else []
    soql_objs: list[str] = []
    for lit in soql_literals:
        soql_objs.extend(_soql_objects(lit))
    callout_detected = bool(
        re.search(r"\bHttpRequest\b|\bHttp\.send\b", source)
        or re.search(r"@future\s*\([^)]*callout\s*=\s*true", source, re.IGNORECASE)
    )
    return {
        "source_body": source,
        "methods": [],
        "class_annotations": [],
        "dml_objects": _dml_objects_from_snippets(dml_snippets),
        "soql_objects": sorted(set(soql_objs)),
        "callout_detected": callout_detected,
        "api_version": _api_version_from_meta(meta_xml),
        "line_count": source.count("\n") + 1,
        "raw_xml_hash": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "parse_error": parser.getNumberOfSyntaxErrors() > 0,
        "trigger_object": trigger_object,
        "trigger_events": trigger_events,
    }
