from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PostSubmitPolicyDecision:
    action: str
    reason: str


class PostSubmitPolicy:
    def __init__(
        self,
        stuck_timeout_seconds: int = 60,
        allow_replace_on_stuck: bool = True,
        cancel_partial_fill: bool = False,
    ):
        self.stuck_timeout_seconds = stuck_timeout_seconds
        self.allow_replace_on_stuck = allow_replace_on_stuck
        self.cancel_partial_fill = cancel_partial_fill

    def decide(self, lifecycle_status: str) -> PostSubmitPolicyDecision:
        if lifecycle_status == "stuck_open":
            if self.allow_replace_on_stuck:
                return PostSubmitPolicyDecision("cancel_replace", "stuck_open_replace")
            return PostSubmitPolicyDecision("cancel", "stuck_open_cancel")
        if lifecycle_status == "partial_fill":
            if self.cancel_partial_fill:
                return PostSubmitPolicyDecision("cancel", "partial_fill_cancel")
            return PostSubmitPolicyDecision("observe", "partial_fill_observe")
        return PostSubmitPolicyDecision("observe", "no_action_needed")
