"""Original synthetic fixtures, not IBM data and not model predictions."""
from datetime import datetime, timedelta, timezone
import random
from aml.domain import Scenario, Transaction


def demo_scenario():
    rng = random.Random(42)
    start = datetime(2026, 9, 22, 8, tzinfo=timezone.utc)
    rows = []
    def add(minute, source, target, amount, label=0, fmt="Wire"):
        rows.append(Transaction(id=f"TX-{len(rows)+1:05d}", timestamp=start + timedelta(minutes=minute), source=source, target=target, amount=amount, label=label, payment_format=fmt))
    for i in range(34):
        add(i * 3, f"RETAIL-{i%7+1:03d}", f"MERCHANT-{i%4+1:03d}", rng.randint(30, 680), fmt="ACH")
    add(12, "NORTHSTAR-01", "HARBOR-02", 24800, 1)
    add(15, "CEDAR-03", "HARBOR-02", 19200, 1)
    add(18, "ORION-04", "HARBOR-02", 28500, 1)
    add(22, "HARBOR-02", "ATLAS-05", 23700, 1)
    add(25, "HARBOR-02", "MERIDIAN-06", 22800, 1)
    add(28, "HARBOR-02", "VALE-07", 24100, 1)
    add(32, "ATLAS-05", "SUMMIT-08", 23100, 1)
    add(35, "MERIDIAN-06", "SUMMIT-08", 22200, 1)
    add(38, "VALE-07", "SUMMIT-08", 23400, 1)
    add(44, "SUMMIT-08", "NORTHSTAR-01", 67200, 1)
    # Legitimate treasury sweep intentionally exercises false alerts.
    add(54, "PAYROLL-01", "TREASURY-02", 34000)
    add(59, "TREASURY-02", "SUPPLIER-03", 32800)
    return Scenario(name="Harbor / layered transfers", origin="demo", description="Original synthetic demonstration • 46 transfers • includes a legitimate treasury sweep", transactions=sorted(rows, key=lambda t: (t.timestamp, t.id)))
