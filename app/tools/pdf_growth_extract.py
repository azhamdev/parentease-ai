"""
Tool: pdf_growth_extract

Extracts child growth data from uploaded PDF documents (KMS, Posyandu cards,
medical check-up reports, etc.) using Mistral OCR, then uses an LLM to parse
structured growth measurements from the raw OCR text.
"""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date

from dotenv import load_dotenv

load_dotenv()


@dataclass
class GrowthMeasurement:
    """A single growth data point extracted from a PDF."""

    measurement_date: str | None = None  # ISO format YYYY-MM-DD
    age_months: int | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    head_circumference_cm: float | None = None
    notes: str | None = None


@dataclass
class GrowthExtractionResult:
    """Full result of the PDF growth extraction pipeline."""

    success: bool
    filename: str
    raw_ocr_text: str = ""
    measurements: list[GrowthMeasurement] = field(default_factory=list)
    child_name: str | None = None
    child_birth_date: str | None = None
    child_gender: str | None = None
    summary: str = ""
    error: str | None = None
    parent_name: str | None = None

    def to_tool_string(self) -> str:
        """Serialise for the LLM system prompt."""
        if not self.success:
            return f"PDF extraction failed for {self.filename}: {self.error}"

        lines = [
            f"Source file: {self.filename}",
        ]
        if self.child_name:
            lines.append(f"Child name: {self.child_name}")
        if self.child_birth_date:
            lines.append(f"Birth date: {self.child_birth_date}")
        if self.child_gender:
            lines.append(f"Gender: {self.child_gender}")
        if self.parent_name:
            lines.append(f"Parent name: {self.parent_name}")

        if self.measurements:
            lines.append(f"Total measurements extracted: {len(self.measurements)}")
            lines.append("Growth data:")
            for i, m in enumerate(self.measurements, 1):
                parts = []
                if m.measurement_date:
                    parts.append(f"date={m.measurement_date}")
                if m.age_months is not None:
                    parts.append(f"age={m.age_months}mo")
                if m.weight_kg is not None:
                    parts.append(f"weight={m.weight_kg}kg")
                if m.height_cm is not None:
                    parts.append(f"height={m.height_cm}cm")
                if m.head_circumference_cm is not None:
                    parts.append(f"head={m.head_circumference_cm}cm")
                if m.notes:
                    parts.append(f"notes={m.notes}")
                lines.append(f"  {i}. {', '.join(parts)}")
        else:
            lines.append("No structured growth measurements could be extracted.")

        if self.summary:
            lines.append(f"Summary: {self.summary}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 1: Mistral OCR
# ---------------------------------------------------------------------------


def _ocr_pdf_with_mistral(pdf_bytes: bytes, filename: str) -> str:
    """Send PDF to Mistral OCR API and return the extracted text."""
    from mistralai.client import Mistral

    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is not set in the environment.")

    client = Mistral(api_key=api_key)

    # Encode PDF as base64 data URI
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    document_url = f"data:application/pdf;base64,{b64}"

    # Use Mistral OCR endpoint
    ocr_response = client.ocr.process(
        model="mistral-ocr-latest",
        document={
            "type": "document_url",
            "document_url": document_url,
        },
    )

    # Collect all page texts
    pages_text: list[str] = []
    if hasattr(ocr_response, "pages") and ocr_response.pages:
        for page in ocr_response.pages:
            if hasattr(page, "markdown") and page.markdown:
                pages_text.append(page.markdown)
            elif hasattr(page, "text") and page.text:
                pages_text.append(page.text)

    return "\n\n---PAGE BREAK---\n\n".join(pages_text) if pages_text else ""


# ---------------------------------------------------------------------------
# Step 2: Parse growth data from OCR text using LLM
# ---------------------------------------------------------------------------

_PARSE_SYSTEM_PROMPT = """You are a data extraction assistant. You will receive raw OCR text 
from a child health document (KMS / Kartu Menuju Sehat, Posyandu card, medical check-up report, 
or similar pediatric health document).

Your task is to extract ALL child growth measurements and child identity data from the text.

Return a JSON object with this exact structure:
{
  "child_name": "string or null",
  "child_birth_date": "YYYY-MM-DD or null",
  "child_gender": "L or P or null",
  "parent_name": "string or null",
  "measurements": [
    {
      "measurement_date": "YYYY-MM-DD or null",
      "age_months": integer or null,
      "weight_kg": float or null,
      "height_cm": float or null,
      "head_circumference_cm": float or null,
      "notes": "string or null",
      "milestone": "string or null",
      "nutrition": "string or null",
      "immunization": "string or null"
    }
  ],
  "summary": "Brief summary of the document content in Indonesian"
}

Rules:
- Extract EVERY measurement row you can find, even partial ones.
- Convert all weights to kg (if given in grams, divide by 1000).
- Convert all heights to cm.
- If a date is ambiguous, use the most likely interpretation.
- If age is given in years, convert to months.
- Return ONLY the JSON, no markdown fences, no explanation.
- If no growth data is found, return empty measurements array and explain in summary.
"""


def _parse_growth_data_with_llm(ocr_text: str) -> dict:
    """Use Mistral LLM to parse structured growth data from OCR text."""
    from mistralai.client import Mistral

    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is not set in the environment.")

    client = Mistral(api_key=api_key)

    # Truncate very long texts to avoid token limits
    truncated = ocr_text[:8000] if len(ocr_text) > 8000 else ocr_text

    response = client.chat.complete(
        model="mistral-large-latest",
        messages=[
            {"role": "system", "content": _PARSE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Extract growth data from this OCR text:\n\n{truncated}",
            },
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    raw_content = response.choices[0].message.content.strip()

    # Strip markdown fences if present
    if raw_content.startswith("```"):
        raw_content = re.sub(r"^```(?:json)?\s*", "", raw_content)
        raw_content = re.sub(r"\s*```$", "", raw_content)

    return json.loads(raw_content)


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------


def extract_growth_from_pdf(
    pdf_bytes: bytes,
    filename: str,
) -> GrowthExtractionResult:
    """
    Full pipeline:
    1. OCR the PDF with Mistral
    2. Parse growth data from OCR text with LLM
    3. Return structured result
    """

    # Step 1: OCR
    try:
        ocr_text = _ocr_pdf_with_mistral(pdf_bytes, filename)
    except Exception as exc:
        return GrowthExtractionResult(
            success=False,
            filename=filename,
            error=f"OCR failed: {exc}",
        )

    if not ocr_text.strip():
        return GrowthExtractionResult(
            success=False,
            filename=filename,
            raw_ocr_text="",
            error="OCR returned empty text. The PDF may be image-only or corrupted.",
        )

    # Step 2: Parse with LLM
    try:
        parsed = _parse_growth_data_with_llm(ocr_text)
    except json.JSONDecodeError as exc:
        return GrowthExtractionResult(
            success=True,
            filename=filename,
            raw_ocr_text=ocr_text,
            summary="OCR succeeded but structured parsing failed. Raw text is available.",
            error=f"JSON parse error: {exc}",
        )
    except Exception as exc:
        return GrowthExtractionResult(
            success=True,
            filename=filename,
            raw_ocr_text=ocr_text,
            summary="OCR succeeded but LLM parsing failed. Raw text is available.",
            error=f"LLM parsing error: {exc}",
        )

    # Step 3: Build result
    measurements: list[GrowthMeasurement] = []
    for m in parsed.get("measurements", []):
        measurements.append(
            GrowthMeasurement(
                measurement_date=m.get("measurement_date"),
                age_months=_safe_int(m.get("age_months")),
                weight_kg=_safe_float(m.get("weight_kg")),
                height_cm=_safe_float(m.get("height_cm")),
                head_circumference_cm=_safe_float(m.get("head_circumference_cm")),
                notes=m.get("notes"),
            )
        )

    return GrowthExtractionResult(
        success=True,
        filename=filename,
        raw_ocr_text=ocr_text,
        measurements=measurements,
        child_name=parsed.get("child_name"),
        child_birth_date=parsed.get("child_birth_date"),
        child_gender=parsed.get("child_gender"),
        summary=parsed.get("summary", ""),
    )


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None
