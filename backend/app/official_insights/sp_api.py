from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import hmac
import json
import os
from pathlib import Path
import time
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlparse
from urllib.request import Request, urlopen


SP_API_ENDPOINTS = {
    "na": "https://sellingpartnerapi-na.amazon.com",
    "eu": "https://sellingpartnerapi-eu.amazon.com",
    "fe": "https://sellingpartnerapi-fe.amazon.com",
}


@dataclass
class SPAPIConfig:
    lwa_client_id: str
    lwa_client_secret: str
    lwa_refresh_token: str
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_session_token: str
    aws_region: str
    endpoint: str

    @classmethod
    def from_env(cls) -> "SPAPIConfig":
        region_key = os.getenv("AMAZON_SPAPI_REGION", "na").strip().lower()
        endpoint = os.getenv("AMAZON_SPAPI_ENDPOINT", "").strip() or SP_API_ENDPOINTS.get(region_key, "")
        if not endpoint:
            raise ValueError("missing AMAZON_SPAPI_ENDPOINT")

        return cls(
            lwa_client_id=os.getenv("AMAZON_SPAPI_CLIENT_ID", "").strip(),
            lwa_client_secret=os.getenv("AMAZON_SPAPI_CLIENT_SECRET", "").strip(),
            lwa_refresh_token=os.getenv("AMAZON_SPAPI_REFRESH_TOKEN", "").strip(),
            aws_access_key_id=os.getenv("AMAZON_SPAPI_AWS_ACCESS_KEY_ID", "").strip(),
            aws_secret_access_key=os.getenv("AMAZON_SPAPI_AWS_SECRET_ACCESS_KEY", "").strip(),
            aws_session_token=os.getenv("AMAZON_SPAPI_AWS_SESSION_TOKEN", "").strip(),
            aws_region=os.getenv("AMAZON_SPAPI_AWS_REGION", "us-east-1").strip(),
            endpoint=endpoint,
        )

    def validate(self) -> None:
        required = {
            "AMAZON_SPAPI_CLIENT_ID": self.lwa_client_id,
            "AMAZON_SPAPI_CLIENT_SECRET": self.lwa_client_secret,
            "AMAZON_SPAPI_REFRESH_TOKEN": self.lwa_refresh_token,
            "AMAZON_SPAPI_AWS_ACCESS_KEY_ID": self.aws_access_key_id,
            "AMAZON_SPAPI_AWS_SECRET_ACCESS_KEY": self.aws_secret_access_key,
            "AMAZON_SPAPI_AWS_REGION": self.aws_region,
            "AMAZON_SPAPI_ENDPOINT": self.endpoint,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"missing SP-API credentials: {', '.join(missing)}")


class SPAPIClient:
    def __init__(self, config: SPAPIConfig) -> None:
        self.config = config
        self._access_token: str | None = None
        self._access_token_expire_at = 0.0

    def ensure_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._access_token_expire_at - 30:
            return self._access_token

        body = urlencode(
            {
                "grant_type": "refresh_token",
                "refresh_token": self.config.lwa_refresh_token,
                "client_id": self.config.lwa_client_id,
                "client_secret": self.config.lwa_client_secret,
            }
        ).encode("utf-8")
        req = Request(
            "https://api.amazon.com/auth/o2/token",
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        )
        with urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        token = str(payload.get("access_token") or "").strip()
        expires = int(payload.get("expires_in") or 3600)
        if not token:
            raise RuntimeError("failed to get lwa access token")

        self._access_token = token
        self._access_token_expire_at = now + max(60, expires)
        return token

    def _sign_headers(
        self,
        *,
        method: str,
        url: str,
        body: bytes,
        access_token: str,
    ) -> dict[str, str]:
        parsed = urlparse(url)
        host = parsed.netloc
        canonical_uri = parsed.path or "/"

        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        query_pairs.sort(key=lambda pair: (pair[0], pair[1]))
        canonical_query = "&".join(
            f"{quote(str(k), safe='-_.~')}={quote(str(v), safe='-_.~')}" for k, v in query_pairs
        )

        amz_date = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        date_stamp = amz_date[:8]
        payload_hash = hashlib.sha256(body).hexdigest()

        headers = {
            "host": host,
            "x-amz-date": amz_date,
            "x-amz-access-token": access_token,
            "x-amz-content-sha256": payload_hash,
        }
        if self.config.aws_session_token:
            headers["x-amz-security-token"] = self.config.aws_session_token

        signed_keys = sorted(headers.keys())
        canonical_headers = "".join(f"{key}:{headers[key].strip()}\n" for key in signed_keys)
        signed_headers = ";".join(signed_keys)

        canonical_request = "\n".join(
            [
                method.upper(),
                canonical_uri,
                canonical_query,
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        credential_scope = f"{date_stamp}/{self.config.aws_region}/execute-api/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )

        def _sign(key: bytes, msg: str) -> bytes:
            return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

        k_date = _sign(f"AWS4{self.config.aws_secret_access_key}".encode("utf-8"), date_stamp)
        k_region = _sign(k_date, self.config.aws_region)
        k_service = _sign(k_region, "execute-api")
        k_signing = _sign(k_service, "aws4_request")
        signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        authorization = (
            "AWS4-HMAC-SHA256 "
            f"Credential={self.config.aws_access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )

        request_headers = {
            "Authorization": authorization,
            "x-amz-access-token": access_token,
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
            "content-type": "application/json",
            "accept": "application/json",
            "host": host,
            "user-agent": "amazon-top-crawler/official-insights",
        }
        if self.config.aws_session_token:
            request_headers["x-amz-security-token"] = self.config.aws_session_token
        return request_headers

    def request_json(
        self,
        *,
        method: str,
        path: str,
        query: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = self.ensure_access_token()
        base_url = self.config.endpoint.rstrip("/")
        query_string = f"?{urlencode(query)}" if query else ""
        url = f"{base_url}{path}{query_string}"
        body = b""
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        headers = self._sign_headers(method=method, url=url, body=body, access_token=token)
        req = Request(url, data=body if method.upper() in {"POST", "PUT", "PATCH"} else None, method=method.upper())
        for key, value in headers.items():
            req.add_header(key, value)

        with urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return {}
            return json.loads(raw)

    def create_report(
        self,
        *,
        report_type: str,
        marketplace_ids: list[str],
        data_start_time: str,
        data_end_time: str,
        report_options: dict[str, Any] | None = None,
    ) -> str:
        body: dict[str, Any] = {
            "reportType": report_type,
            "marketplaceIds": marketplace_ids,
            "dataStartTime": data_start_time,
            "dataEndTime": data_end_time,
        }
        if report_options:
            body["reportOptions"] = report_options

        payload = self.request_json(method="POST", path="/reports/2021-06-30/reports", payload=body)
        report_id = str(payload.get("reportId") or "").strip()
        if not report_id:
            raise RuntimeError(f"failed to create report: {payload}")
        return report_id

    def get_report(self, report_id: str) -> dict[str, Any]:
        return self.request_json(method="GET", path=f"/reports/2021-06-30/reports/{quote(report_id)}")

    def wait_report_document_id(
        self,
        report_id: str,
        *,
        timeout_seconds: int = 900,
        poll_interval_seconds: int = 20,
    ) -> tuple[str | None, str]:
        deadline = time.time() + max(10, timeout_seconds)
        while time.time() < deadline:
            report = self.get_report(report_id)
            status = str(report.get("processingStatus") or "").strip()
            if status == "DONE":
                return str(report.get("reportDocumentId") or "").strip() or None, status
            if status in {"CANCELLED", "FATAL", "DONE_NO_DATA"}:
                return None, status
            time.sleep(max(1, poll_interval_seconds))
        return None, "TIMEOUT"

    def get_report_document(self, report_document_id: str) -> dict[str, Any]:
        return self.request_json(
            method="GET",
            path=f"/reports/2021-06-30/documents/{quote(report_document_id)}",
        )

    def download_report_document(self, document: dict[str, Any], output_path: Path) -> None:
        url = str(document.get("url") or "").strip()
        if not url:
            raise RuntimeError("report document missing download url")

        req = Request(url, method="GET")
        with urlopen(req, timeout=120) as resp:
            content = resp.read()

        algorithm = str(document.get("compressionAlgorithm") or "").strip().upper()
        if algorithm == "GZIP":
            content = gzip.decompress(content)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(content)


def fetch_report_to_file(
    *,
    client: SPAPIClient,
    report_type: str,
    marketplace_ids: list[str],
    output_path: Path,
    data_start_time: str,
    data_end_time: str,
    report_options: dict[str, Any] | None = None,
    timeout_seconds: int = 900,
    poll_interval_seconds: int = 20,
) -> dict[str, Any]:
    report_id = client.create_report(
        report_type=report_type,
        marketplace_ids=marketplace_ids,
        data_start_time=data_start_time,
        data_end_time=data_end_time,
        report_options=report_options,
    )
    document_id, status = client.wait_report_document_id(
        report_id,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )

    result = {
        "report_type": report_type,
        "report_id": report_id,
        "status": status,
        "output_path": str(output_path),
    }

    if not document_id:
        return result

    document = client.get_report_document(document_id)
    client.download_report_document(document, output_path)
    result["report_document_id"] = document_id
    return result

