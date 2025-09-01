"""
Identity Validation Utilities

Reusable validators for proxy headers, event envelope metadata, and
registration responses. Designed for use in functional/E2E tests without
mixing abstraction layers.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class IdentityValidator:
    """Validates identity threading through client → proxy → events."""

    @staticmethod
    def validate_proxy_headers(headers: Dict[str, str]) -> Dict[str, Any]:
        """Verify X-User-ID, optional X-Org-ID, and X-Correlation-ID headers.

        Returns a dict summary with booleans and extracted values.
        """
        x_user = headers.get("X-User-ID")
        x_org = headers.get("X-Org-ID")
        x_corr = headers.get("X-Correlation-ID")

        result = {
            "has_user": bool(x_user),
            "has_org": bool(x_org),
            "has_correlation": bool(x_corr),
            "user_id": x_user,
            "org_id": x_org,
            "correlation_id": x_corr,
        }
        if not result["has_user"]:
            raise AssertionError("Missing X-User-ID in forwarded headers")
        if not result["has_correlation"]:
            raise AssertionError("Missing X-Correlation-ID in forwarded headers")
        return result

    @staticmethod
    def validate_event_metadata(envelope: Dict[str, Any]) -> Dict[str, Any]:
        """Verify org_id in EventEnvelope.metadata when present.

        Accepts an EventEnvelope-like dict as produced by tests.
        """
        metadata = envelope.get("metadata") or envelope.get("data", {}).get("metadata") or {}
        org_id = metadata.get("org_id")
        return {"metadata_present": bool(metadata), "org_id": org_id}

    @staticmethod
    def validate_event_identity(envelope: Dict[str, Any]) -> Dict[str, Any]:
        """Inspect event payload for identity fields (user_id/org_id).

        Works with EventEnvelope where payload lives in envelope["data"].
        """
        payload = envelope.get("data", {})
        user_id = payload.get("user_id")
        org_id = payload.get("org_id")
        return {
            "user_id": user_id,
            "org_id": org_id,
            "has_user": user_id is not None and user_id != "",
            "has_org": org_id is not None and str(org_id).strip() != "",
        }

    @staticmethod
    def validate_batch_registration_identity(response_json: Dict[str, Any]) -> Dict[str, Any]:
        """Verify identity-related fields in AGW/BOS registration responses.

        Ensures presence of batch_id and correlation_id.
        """
        batch_id = response_json.get("batch_id")
        correlation_id = response_json.get("correlation_id")
        if not batch_id:
            raise AssertionError("Registration response missing 'batch_id'")
        if not correlation_id:
            raise AssertionError("Registration response missing 'correlation_id'")
        return {"batch_id": batch_id, "correlation_id": correlation_id}

    @staticmethod
    def validate_agw_registration_identity(response_json: Dict[str, Any]) -> Dict[str, Any]:
        """Lightweight AGW registration identity validator for client-like flows."""
        return IdentityValidator.validate_batch_registration_identity(response_json)

    @staticmethod
    def validate_identity_consistency(
        agw_response: Dict[str, Any],
        event_envelope: Dict[str, Any],
        db_record: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Composite identity validator for targeted service-scoped tests.

        Avoid using this in cross-cutting functional tests to prevent mixing
        abstraction levels (see Rules 070/075). Intended for focused scenarios
        where all three artifacts are available and stable.
        """
        reg = IdentityValidator.validate_batch_registration_identity(agw_response)
        evt = IdentityValidator.validate_event_identity(event_envelope)
        result = {"registration": reg, "event": evt}

        if db_record is not None:
            db_user = db_record.get("user_id")
            db_org = db_record.get("org_id")
            result["db"] = {"user_id": db_user, "org_id": db_org}
            if evt["has_user"] and db_user and evt["user_id"] != db_user:
                raise AssertionError("Event user_id does not match DB record")
            if evt["has_org"] and db_org is not None and str(evt["org_id"]) != str(db_org):
                raise AssertionError("Event org_id does not match DB record")

        return result
