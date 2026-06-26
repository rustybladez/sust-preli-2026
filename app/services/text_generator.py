from __future__ import annotations

import json
import logging
from typing import Any

from app.config import Settings
from app.schemas.enums import CaseType, Department, EvidenceVerdict

logger = logging.getLogger(__name__)


class TextGenerator:
    """Template-first text generation with optional LLM polish."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def generate(
        self,
        *,
        complaint: str,
        case_type: CaseType,
        department: Department,
        evidence: EvidenceVerdict,
        matched_id: str | None,
        reply_language: str,
        txn_summary: str | None,
    ) -> tuple[str, str, str]:
        summary, action, reply = self._templates(
            case_type=case_type,
            department=department,
            evidence=evidence,
            matched_id=matched_id,
            reply_language=reply_language,
            txn_summary=txn_summary,
        )

        if self._settings.llm_enabled:
            llm_text = await self._maybe_llm_enhance(
                complaint=complaint,
                case_type=case_type,
                department=department,
                evidence=evidence,
                matched_id=matched_id,
                reply_language=reply_language,
                txn_summary=txn_summary,
                fallback=(summary, action, reply),
            )
            if llm_text:
                return llm_text

        return summary, action, reply

    def _templates(
        self,
        *,
        case_type: CaseType,
        department: Department,
        evidence: EvidenceVerdict,
        matched_id: str | None,
        reply_language: str,
        txn_summary: str | None,
    ) -> tuple[str, str, str]:
        txn_ref = matched_id or "the reported transaction"
        dept_name = department.value.replace("_", " ")

        if case_type == CaseType.PHISHING_OR_SOCIAL_ENGINEERING:
            summary = (
                "Customer reports an unsolicited contact asking for OTP or credentials. "
                "Customer has not shared sensitive information."
            )
            action = (
                "Escalate to fraud_risk immediately. Log the reported contact for pattern analysis."
            )
            if reply_language == "bn":
                reply = (
                    "যোগাযোগ করার জন্য ধন্যবাদ। আমরা কোনো অবস্থাতেই OTP, PIN বা পাসওয়ার্ড "
                    "চাই না। অনুগ্রহ করে কারো সাথে এই তথ্য শেয়ার করবেন না। "
                    "আমাদের ফ্রড দলকে জানানো হয়েছে।"
                )
            else:
                reply = (
                    "Thank you for reaching out before sharing any information. "
                    "We never ask for your PIN, OTP, or password under any circumstances. "
                    "Please do not share these with anyone, even if they claim to be from us. "
                    "Our fraud team has been notified of this incident."
                )
            return summary, action, reply

        if case_type == CaseType.OTHER and evidence == EvidenceVerdict.INSUFFICIENT_DATA:
            summary = (
                "Customer reports a vague concern without enough detail to identify a transaction."
            )
            action = (
                "Reply asking for transaction ID, amount, approximate time, and issue description."
            )
            if reply_language == "bn":
                reply = (
                    "যোগাযোগ করার জন্য ধন্যবাদ। দ্রুত সহায়তার জন্য লেনদেন ID, "
                    "পরিমাণ এবং সমস্যার সংক্ষিপ্ত বিবরণ শেয়ার করুন।"
                )
            else:
                reply = (
                    "Thank you for reaching out. To help you faster, please share the transaction ID, "
                    "the amount involved, and a short description of what went wrong."
                )
            return summary, action, reply

        if (
            case_type == CaseType.WRONG_TRANSFER
            and evidence == EvidenceVerdict.INSUFFICIENT_DATA
            and matched_id is None
        ):
            summary = (
                "Customer reports an unreceived transfer, but multiple similar transactions "
                "exist and the correct one cannot be determined."
            )
            action = (
                "Ask the customer for the recipient number before initiating any dispute workflow."
            )
            reply = (
                "Thank you for reaching out. We see multiple similar transactions on that date. "
                "Could you share the recipient's number so we can identify the right transaction?"
            )
            return summary, action, reply

        builders = {
            CaseType.WRONG_TRANSFER: self._wrong_transfer,
            CaseType.PAYMENT_FAILED: self._payment_failed,
            CaseType.REFUND_REQUEST: self._refund_request,
            CaseType.DUPLICATE_PAYMENT: self._duplicate_payment,
            CaseType.MERCHANT_SETTLEMENT_DELAY: self._merchant_settlement,
            CaseType.AGENT_CASH_IN_ISSUE: self._agent_cash_in,
        }
        builder = builders.get(case_type, self._generic)
        return builder(
            matched_id=matched_id,
            evidence=evidence,
            reply_language=reply_language,
            txn_summary=txn_summary,
            dept_name=dept_name,
            txn_ref=txn_ref,
        )

    def _wrong_transfer(
        self,
        *,
        matched_id: str | None,
        evidence: EvidenceVerdict,
        reply_language: str,
        txn_summary: str | None,
        dept_name: str,
        txn_ref: str,
    ) -> tuple[str, str, str]:
        summary = txn_summary or (
            f"Customer reports a wrong transfer related to {txn_ref}."
        )
        if evidence == EvidenceVerdict.INCONSISTENT:
            summary += " Prior transfers to the same recipient suggest an established pattern."
            action = (
                f"Flag {txn_ref} for human review and verify whether this was genuinely a wrong transfer."
            )
        else:
            action = (
                f"Verify {txn_ref} details with the customer and initiate the wrong-transfer dispute workflow."
            )

        if reply_language == "bn":
            reply = (
                f"আপনার {txn_ref} লেনদেন সম্পর্কে আমরা অবগত হয়েছি। "
                f"আমাদের {dept_name} দল যাচাই করে অফিসিয়াল চ্যানেলে যোগাযোগ করবে।"
            )
        else:
            reply = (
                f"We have noted your concern about transaction {txn_ref}. "
                f"Our dispute team will review the case and contact you through official support channels."
            )
        return summary, action, reply

    def _payment_failed(
        self,
        *,
        matched_id: str | None,
        evidence: EvidenceVerdict,
        reply_language: str,
        txn_summary: str | None,
        dept_name: str,
        txn_ref: str,
    ) -> tuple[str, str, str]:
        summary = txn_summary or (
            f"Customer reports a failed payment ({txn_ref}) with possible balance deduction."
        )
        action = (
            f"Investigate {txn_ref} ledger status and initiate automatic reversal flow if needed."
        )
        reply = (
            f"We have noted that transaction {txn_ref} may have caused an unexpected balance deduction. "
            f"Our payments team will review the case and any eligible amount will be returned "
            f"through official channels."
        )
        return summary, action, reply

    def _refund_request(
        self,
        *,
        matched_id: str | None,
        evidence: EvidenceVerdict,
        reply_language: str,
        txn_summary: str | None,
        dept_name: str,
        txn_ref: str,
    ) -> tuple[str, str, str]:
        summary = txn_summary or (
            f"Customer requests a refund for completed payment {txn_ref}."
        )
        action = (
            "Explain merchant refund policy and guide the customer to contact the merchant directly."
        )
        reply = (
            "Thank you for reaching out. Refunds for completed merchant payments depend on the "
            "merchant's own policy. We recommend contacting the merchant directly. "
            "If you need help reaching them, please reply and we will guide you."
        )
        return summary, action, reply

    def _duplicate_payment(
        self,
        *,
        matched_id: str | None,
        evidence: EvidenceVerdict,
        reply_language: str,
        txn_summary: str | None,
        dept_name: str,
        txn_ref: str,
    ) -> tuple[str, str, str]:
        summary = txn_summary or (
            f"Customer reports duplicate payment; suspected duplicate is {txn_ref}."
        )
        action = (
            f"Verify duplicate with payments_ops and initiate reversal review for {txn_ref} if confirmed."
        )
        reply = (
            f"We have noted the possible duplicate payment for transaction {txn_ref}. "
            f"Our payments team will verify with the biller and any eligible amount will be returned "
            f"through official channels."
        )
        return summary, action, reply

    def _merchant_settlement(
        self,
        *,
        matched_id: str | None,
        evidence: EvidenceVerdict,
        reply_language: str,
        txn_summary: str | None,
        dept_name: str,
        txn_ref: str,
    ) -> tuple[str, str, str]:
        summary = txn_summary or (
            f"Merchant reports delayed settlement for {txn_ref}."
        )
        action = (
            f"Route to merchant_operations to verify settlement batch status for {txn_ref}."
        )
        reply = (
            f"We have noted your concern about settlement {txn_ref}. "
            f"Our merchant operations team will check the batch status and update you "
            f"through official channels."
        )
        return summary, action, reply

    def _agent_cash_in(
        self,
        *,
        matched_id: str | None,
        evidence: EvidenceVerdict,
        reply_language: str,
        txn_summary: str | None,
        dept_name: str,
        txn_ref: str,
    ) -> tuple[str, str, str]:
        summary = txn_summary or (
            f"Customer reports cash-in via agent not reflected in balance ({txn_ref})."
        )
        action = (
            f"Investigate {txn_ref} pending status with agent operations and resolve within SLA."
        )
        if reply_language == "bn":
            reply = (
                f"আপনার লেনদেন {txn_ref} এর বিষয়ে আমরা অবগত হয়েছি। "
                f"আমাদের এজেন্ট অপারেশন্স দল এটি দ্রুত যাচাই করবে এবং "
                f"অফিসিয়াল চ্যানেলে আপনাকে জানাবে।"
            )
        else:
            reply = (
                f"We have noted your cash-in concern for transaction {txn_ref}. "
                f"Our agent operations team will investigate and update you through official channels."
            )
        return summary, action, reply

    def _generic(
        self,
        *,
        matched_id: str | None,
        evidence: EvidenceVerdict,
        reply_language: str,
        txn_summary: str | None,
        dept_name: str,
        txn_ref: str,
    ) -> tuple[str, str, str]:
        summary = txn_summary or "Customer reported an issue requiring support review."
        action = "Review the ticket details and request clarification if needed."
        reply = (
            "Thank you for reaching out. Our support team will review your case "
            "and contact you through official support channels."
        )
        return summary, action, reply

    async def _maybe_llm_enhance(
        self,
        *,
        complaint: str,
        case_type: CaseType,
        department: Department,
        evidence: EvidenceVerdict,
        matched_id: str | None,
        reply_language: str,
        txn_summary: str | None,
        fallback: tuple[str, str, str],
    ) -> tuple[str, str, str] | None:
        try:
            from app.services.llm.client import generate_text_fields

            return await generate_text_fields(
                settings=self._settings,
                context={
                    "complaint": complaint,
                    "case_type": case_type.value,
                    "department": department.value,
                    "evidence_verdict": evidence.value,
                    "relevant_transaction_id": matched_id,
                    "reply_language": reply_language,
                    "txn_summary": txn_summary,
                },
                fallback=fallback,
            )
        except Exception:
            logger.exception("LLM enhancement failed; using templates")
            return None
