"""Same causal feature representation for Colab and local inference."""
from collections import defaultdict, deque, Counter
from dataclasses import dataclass, field
import math
from aml.domain import Transaction

FEATURE_VERSION = "causal-24h-v2"
QUESTION = {"t": "noul", "ins": "Does this transaction participate in money laundering?", "crit": None}
NUMERIC_FEATURES = ["log_amount", "source_out_count", "source_in_count", "target_in_count", "source_peers", "target_senders", "source_in_value", "source_out_value", "minutes_since_in", "amount_to_prior_mean"]


@dataclass
class AccountHistory:
    incoming: int = 0
    outgoing: int = 0
    senders: Counter = field(default_factory=Counter)
    receivers: Counter = field(default_factory=Counter)
    incoming_value: dict = field(default_factory=lambda: defaultdict(float))
    outgoing_value: dict = field(default_factory=lambda: defaultdict(float))
    outgoing_count: Counter = field(default_factory=Counter)
    incoming_times: dict = field(default_factory=lambda: defaultdict(deque))


class History:
    def __init__(self):
        self.events = deque()
        self.accounts = defaultdict(AccountHistory)
        self.pending = []
        self.last_time = None

    def _update(self, tx, direction):
        sender, receiver = self.accounts[tx.source], self.accounts[tx.target]
        sender.outgoing += direction
        receiver.incoming += direction
        sender.receivers[tx.target] += direction
        receiver.senders[tx.source] += direction
        sender.outgoing_value[tx.currency] += direction * tx.amount
        receiver.incoming_value[tx.currency] += direction * tx.amount
        sender.outgoing_count[tx.currency] += direction
        if direction == 1:
            receiver.incoming_times[tx.currency].append(tx.timestamp.timestamp())
        else:
            receiver.incoming_times[tx.currency].popleft()
            if not receiver.incoming_times[tx.currency]:
                del receiver.incoming_times[tx.currency]
            if not sender.receivers[tx.target]:
                del sender.receivers[tx.target]
            if not receiver.senders[tx.source]:
                del receiver.senders[tx.source]
            for account in {tx.source, tx.target}:
                stats = self.accounts[account]
                if stats.incoming == 0 and stats.outgoing == 0:
                    del self.accounts[account]

    def observe(self, tx: Transaction):
        now = tx.timestamp.timestamp()
        if self.last_time is not None and now < self.last_time:
            raise ValueError("Transactions must be chronological")
        if now != self.last_time:
            for previous in self.pending:
                self._update(previous, 1)
                self.events.append(previous)
            self.pending = []
        self.last_time = now
        while self.events and self.events[0].timestamp.timestamp() < now - 86400:
            old = self.events.popleft()
            self._update(old, -1)
        # Pending equal-time transactions are not committed until time advances.
        sender = self.accounts.get(tx.source) or AccountHistory()
        receiver = self.accounts.get(tx.target) or AccountHistory()
        outgoing_n = sender.outgoing_count.get(tx.currency, 0)
        mean = sender.outgoing_value.get(tx.currency, 0) / outgoing_n if outgoing_n else tx.amount
        prior_in = sender.incoming_times.get(tx.currency)
        f = {
            "log_amount": round(math.log1p(tx.amount), 4),
            "source_out_count": sender.outgoing, "source_in_count": sender.incoming,
            "target_in_count": receiver.incoming,
            "source_peers": len(sender.receivers),
            "target_senders": len(receiver.senders),
            "source_in_value": round(max(0, sender.incoming_value.get(tx.currency, 0)), 2),
            "source_out_value": round(max(0, sender.outgoing_value.get(tx.currency, 0)), 2),
            "minutes_since_in": round((now - prior_in[-1]) / 60, 2) if prior_in else -1,
            "amount_to_prior_mean": round(tx.amount / max(mean, 0.01), 3),
        }
        self.pending.append(tx)
        return f


def model_state(tx, f):
    # Raw account IDs and ground truth are deliberately absent.
    return {"amount": tx.amount, "currency": tx.currency, "format": tx.payment_format, "self_transfer": tx.source == tx.target, "hour_utc": tx.timestamp.hour, "history_24h": f}


def rule_score(tx, f):
    reasons = []
    score = 0.08
    if 0 <= f["minutes_since_in"] <= 30 and f["source_in_value"] > 0:
        score += 0.42
        reasons.append("Rapid onward transfer: incoming funds within 30 minutes")
    if f["target_senders"] >= 2:
        score += 0.22
        reasons.append("Fan-in candidate: multiple senders to the receiving account")
    if f["source_peers"] >= 2:
        score += 0.20
        reasons.append("Fan-out candidate: transfers to multiple counterparties")
    if f["amount_to_prior_mean"] > 4:
        score += 0.18
        reasons.append("Amount exceeds four times the sender's prior mean in this currency")
    return round(min(score, 0.97), 4), reasons
