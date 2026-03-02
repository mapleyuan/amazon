from __future__ import annotations

from dataclasses import dataclass

VALID_SITES = {"amazon.com", "amazon.co.jp", "amazon.co.uk"}
VALID_BOARDS = {"best_sellers", "new_releases", "movers_and_shakers"}


@dataclass(slots=True)
class JobRunRequest:
    site: str
    board_type: str


class ValidationError(ValueError):
    pass


def parse_job_run_payload(payload: dict) -> JobRunRequest:
    site = str(payload.get("site", "")).strip().lower()
    board = str(payload.get("board_type", "")).strip().lower()

    if site not in VALID_SITES:
        raise ValidationError(f"unsupported site: {site}")
    if board not in VALID_BOARDS:
        raise ValidationError(f"unsupported board_type: {board}")

    return JobRunRequest(site=site, board_type=board)
