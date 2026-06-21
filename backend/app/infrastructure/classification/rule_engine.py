"""Phase-1 rule-based classifier (ADR 0004).

Maps instrument-tag prefixes to symbol types using longest-prefix matching. Deterministic and
explainable; ML/ViT classifiers implement the same ``SymbolClassifier`` port and drop in later.
"""

from __future__ import annotations

import re

from ...domain.enums import ClassificationMethod, SymbolType
from ...domain.ports import SymbolClassifier
from ...domain.value_objects import Classification

# Ordered longest-first so 'PIC' wins over 'P', 'HEX' over 'H', etc.
_PREFIX_RULES: list[tuple[str, SymbolType]] = sorted(
    [
        ("XV", SymbolType.VALVE),
        ("FV", SymbolType.VALVE),
        ("PCV", SymbolType.VALVE),
        ("PV", SymbolType.PRESSURE_VESSEL),
        ("HEX", SymbolType.HEAT_EXCHANGER),
        ("E", SymbolType.HEAT_EXCHANGER),
        ("PT", SymbolType.PRESSURE_TRANSMITTER),
        ("FT", SymbolType.INSTRUMENT),
        ("LT", SymbolType.INSTRUMENT),
        ("TT", SymbolType.INSTRUMENT),
        ("PIC", SymbolType.CONTROLLER),
        ("FIC", SymbolType.CONTROLLER),
        ("LIC", SymbolType.CONTROLLER),
        ("P", SymbolType.PUMP),
        ("C", SymbolType.COMPRESSOR),
        ("TK", SymbolType.TANK),
        ("T", SymbolType.TANK),
    ],
    key=lambda r: len(r[0]),
    reverse=True,
)

_TAG = re.compile(r"^([A-Za-z]+)")


class RuleBasedClassifier(SymbolClassifier):
    def classify(self, *, label: str | None, crop_png: bytes | None) -> Classification:
        if label:
            match = _TAG.match(label.strip().upper())
            if match:
                prefix = match.group(1)
                for rule_prefix, symbol_type in _PREFIX_RULES:
                    if prefix.startswith(rule_prefix):
                        return Classification(
                            symbol_type=symbol_type,
                            method=ClassificationMethod.RULE,
                            confidence=0.95,
                            raw_class=rule_prefix,
                        )
        return Classification(
            symbol_type=SymbolType.UNKNOWN,
            method=ClassificationMethod.RULE,
            confidence=0.1,
            raw_class=None,
        )
