"""LLM second-pass classifier (DRT-5204 §2.3).

Single Claude `messages.create` call per hospital, using strict tool-use to
force a structured `classify_hospital(...)` output. The classifier owns one
behavior: turn `(raw_place, RuleLabel)` into an `LLMLabel`.

Multi-turn tool calls (`fetch_google_place_details`, `fetch_website_text`)
are deferred — research §4.2 listed them as PR 3 candidates but the v1 of
the pipeline ships with single-call classification driven by the raw Google
Place data we already fetched. The multi-turn loop slots in here later
without touching callers.

If the LLM hallucinates a `chain_brand_normalized` that disagrees with the
rule layer's match, we halve the confidence and flag `needs_review` so the
backoffice queue picks it up.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

import structlog

from hospital.vars import HospitalAppointmentMode, HospitalOwnership, HospitalServiceTag
from services.external.anthropic.client import get_client as get_anthropic_client

from .rules import RuleLabel

logger = structlog.get_logger(__name__)

_MODEL = 'claude-haiku-4-5-20251001'
_MAX_TOKENS = 1024


CLASSIFY_HOSPITAL_TOOL: dict = {
    'name': 'classify_hospital',
    'description': (
        'Output the final classification for a single US vet hospital. '
        'Call this exactly once after considering name, address, '
        'opening hours, and types from Google Places.'
    ),
    'input_schema': {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'ownership': {
                'type': 'string',
                'enum': [v.value for v in HospitalOwnership],
            },
            'service_tags': {
                'type': 'array',
                'items': {
                    'type': 'string',
                    'enum': [v.value for v in HospitalServiceTag],
                },
                'uniqueItems': True,
            },
            'specialty_areas': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': (
                    'Specific specialty fields (e.g. "cardiology", '
                    '"oncology", "ophthalmology"). Fill only when SPECIALTY '
                    'is among service_tags; otherwise return an empty array.'
                ),
            },
            'appointment_mode': {
                'type': 'string',
                'enum': [v.value for v in HospitalAppointmentMode],
            },
            'chain_brand_normalized': {'type': ['string', 'null']},
            'confidence': {'type': 'number', 'minimum': 0.0, 'maximum': 1.0},
            'reasoning': {'type': 'string', 'maxLength': 500},
        },
        'required': [
            'ownership', 'service_tags', 'specialty_areas',
            'appointment_mode', 'confidence', 'reasoning',
        ],
    },
}


@dataclass
class LLMLabel:
    ownership: HospitalOwnership
    service_tags: tuple[HospitalServiceTag, ...]
    appointment_mode: HospitalAppointmentMode
    confidence: Decimal
    specialty_areas: tuple[str, ...] = ()
    chain_brand_normalized: str | None = None
    reasoning: str = ''
    needs_review: bool = False
    input_tokens: int = 0
    output_tokens: int = 0

    @classmethod
    def needs_review_fallback(cls, reasoning: str = '') -> 'LLMLabel':
        return cls(
            ownership=HospitalOwnership.UNCLASSIFIED,
            service_tags=(),
            appointment_mode=HospitalAppointmentMode.UNKNOWN,
            confidence=Decimal('0.3'),
            reasoning=reasoning,
            needs_review=True,
        )


def _build_user_message(raw_place: dict, rule_label: RuleLabel) -> dict:
    place_summary = {
        'displayName': (raw_place.get('displayName') or {}).get('text'),
        'formattedAddress': raw_place.get('formattedAddress'),
        'types': raw_place.get('types'),
        'primaryType': raw_place.get('primaryType'),
        'websiteUri': raw_place.get('websiteUri'),
        'nationalPhoneNumber': raw_place.get('nationalPhoneNumber'),
        'rating': raw_place.get('rating'),
        'userRatingCount': raw_place.get('userRatingCount'),
        'businessStatus': raw_place.get('businessStatus'),
        'currentOpeningHours': raw_place.get('currentOpeningHours'),
    }
    hint_lines = []
    if rule_label.matched:
        hint_lines.append(
            f"Rule-pass hint: chain_brand_normalized={rule_label.chain_brand_normalized!r}, "
            f"ownership={rule_label.ownership}, service_tags={list(rule_label.service_tags)}. "
            f"Confirm or override based on the Google Places data below."
        )
    text = (
        'Classify the US vet hospital below.\n'
        + ('\n'.join(hint_lines) + '\n' if hint_lines else '')
        + '\nGoogle Places record:\n```json\n'
        + json.dumps(place_summary, ensure_ascii=False, indent=2)
        + '\n```\n'
    )
    return {'role': 'user', 'content': text}


def _extract_classify_call(response: dict) -> dict | None:
    for block in response.get('content', []):
        if isinstance(block, dict) and block.get('type') == 'tool_use' \
                and block.get('name') == 'classify_hospital':
            return block.get('input') or {}
        # Anthropic SDK returns typed objects, but `model_dump`-equivalents
        # are accessible via attribute too. Support both shapes.
        if hasattr(block, 'type') and getattr(block, 'type') == 'tool_use' \
                and getattr(block, 'name', None) == 'classify_hospital':
            return getattr(block, 'input', None) or {}
    return None


def _parse_label(payload: dict) -> LLMLabel:
    ownership = HospitalOwnership(payload['ownership'])
    service_tags = tuple(
        HospitalServiceTag(v) for v in payload.get('service_tags') or []
    )
    appt = HospitalAppointmentMode(payload['appointment_mode'])
    confidence = Decimal(str(payload['confidence'])).quantize(Decimal('0.001'))
    specialty_areas = tuple(
        str(s) for s in payload.get('specialty_areas') or []
    )
    return LLMLabel(
        ownership=ownership,
        service_tags=service_tags,
        appointment_mode=appt,
        confidence=confidence,
        specialty_areas=specialty_areas,
        chain_brand_normalized=payload.get('chain_brand_normalized'),
        reasoning=payload.get('reasoning') or '',
    )


def _cross_check_against_rule(label: LLMLabel, rule_label: RuleLabel) -> LLMLabel:
    """Halve confidence + flag review when LLM picks a different chain
    than the rule layer's regex match (DRT-5204 §3.3)."""

    if not rule_label.matched:
        return label
    if not label.chain_brand_normalized:
        return label
    if label.chain_brand_normalized == rule_label.chain_brand_normalized:
        return label
    halved = (label.confidence / Decimal(2)).quantize(Decimal('0.001'))
    return LLMLabel(
        ownership=label.ownership,
        service_tags=label.service_tags,
        appointment_mode=label.appointment_mode,
        confidence=halved,
        specialty_areas=label.specialty_areas,
        chain_brand_normalized=label.chain_brand_normalized,
        reasoning=label.reasoning + ' [chain_brand mismatch with rule layer]',
        needs_review=True,
        input_tokens=label.input_tokens,
        output_tokens=label.output_tokens,
    )


def _normalize_response(response) -> dict:
    """Anthropic SDK returns a typed object; normalize to a dict so the rest
    of the module is decoupled from SDK shape changes."""

    if isinstance(response, dict):
        return response
    if hasattr(response, 'model_dump'):
        return response.model_dump()  # pydantic v2 (anthropic >=0.40)
    return {}


class HospitalClassifier:
    """One Anthropic call per hospital. Stateless except for the SDK client."""

    NEEDS_REVIEW_THRESHOLD = Decimal('0.7')

    def __init__(self) -> None:
        self.client = get_anthropic_client()

    def classify(self, raw_place: dict, rule_label: RuleLabel) -> LLMLabel:
        try:
            sdk_response = self.client.messages.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                tools=[CLASSIFY_HOSPITAL_TOOL],
                tool_choice={'type': 'tool', 'name': 'classify_hospital'},
                messages=[_build_user_message(raw_place, rule_label)],
            )
        except Exception:
            logger.exception(
                'sourcing.classifier.llm_error',
                place_id=raw_place.get('id'),
            )
            # SDK error: no usage to attribute, fallback with zero tokens.
            return LLMLabel.needs_review_fallback(reasoning='LLM call failed')

        # Token attribution happens before any structural fallback so the
        # cost the API actually charged us still lands in
        # `SourcingJob.llm_*_tokens` even when the parse fails.
        response = _normalize_response(sdk_response)
        usage = response.get('usage') or {}
        input_tok = int(usage.get('input_tokens') or 0)
        output_tok = int(usage.get('output_tokens') or 0)

        payload = _extract_classify_call(response)
        if not payload:
            logger.warning(
                'sourcing.classifier.no_tool_call',
                place_id=raw_place.get('id'),
            )
            fb = LLMLabel.needs_review_fallback(
                reasoning='LLM did not produce a classify_hospital tool call',
            )
            fb.input_tokens = input_tok
            fb.output_tokens = output_tok
            return fb
        try:
            label = _parse_label(payload)
        except Exception:
            logger.exception(
                'sourcing.classifier.parse_error',
                place_id=raw_place.get('id'),
                payload=payload,
            )
            fb = LLMLabel.needs_review_fallback(
                reasoning='LLM output failed schema validation',
            )
            fb.input_tokens = input_tok
            fb.output_tokens = output_tok
            return fb

        label.input_tokens = input_tok
        label.output_tokens = output_tok

        # Cross-check against rule layer's chain match.
        label = _cross_check_against_rule(label, rule_label)

        # NEEDS_REVIEW queue threshold.
        if label.confidence < self.NEEDS_REVIEW_THRESHOLD:
            label.needs_review = True

        return label
