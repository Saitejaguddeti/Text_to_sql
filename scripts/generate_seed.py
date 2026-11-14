"""Generate db/init/02_seed.sql: a small, made-up retail-banking dataset.

The output is deterministic (fixed random seed), so re-running it gives the same file.
Run from the repo root:  python scripts/generate_seed.py
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "db" / "init" / "02_seed.sql"
START, END = date(2026, 4, 1), date(2026, 9, 30)
rng = random.Random(2026)

BRANCHES = [
    (1, "Uptown Charlotte", "Charlotte", "NC"),
    (2, "Ballantyne", "Charlotte", "NC"),
    (3, "Raleigh Downtown", "Raleigh", "NC"),
    (4, "Midtown Atlanta", "Atlanta", "GA"),
    (5, "Uptown Dallas", "Dallas", "TX"),
    (6, "Scottsdale", "Phoenix", "AZ"),
]
FIRST = [
    "Aarav",
    "Maya",
    "James",
    "Priya",
    "Daniel",
    "Grace",
    "Rohan",
    "Emily",
    "Carlos",
    "Hannah",
    "Vikram",
    "Olivia",
    "Marcus",
    "Sneha",
    "Ethan",
    "Leah",
    "Arjun",
    "Sofia",
    "Nathan",
    "Ananya",
    "Lucas",
    "Chloe",
    "Kiran",
    "Isabella",
    "Owen",
    "Meera",
    "Tyler",
    "Ava",
    "Rahul",
    "Zoe",
]
LAST = [
    "Patel",
    "Johnson",
    "Reddy",
    "Smith",
    "Garcia",
    "Nguyen",
    "Williams",
    "Kumar",
    "Brown",
    "Davis",
    "Shah",
    "Miller",
    "Rao",
    "Wilson",
    "Lopez",
    "Anderson",
    "Iyer",
    "Thomas",
    "Martin",
    "Chen",
]
MERCHANTS = [
    ("Harris Teeter", "groceries", 25, 180),
    ("Publix", "groceries", 20, 160),
    ("Costco", "groceries", 60, 320),
    ("Shell", "fuel", 30, 75),
    ("QuikTrip", "fuel", 25, 70),
    ("Amazon", "shopping", 12, 240),
    ("Target", "shopping", 15, 190),
    ("Best Buy", "electronics", 40, 900),
    ("Starbucks", "dining", 5, 18),
    ("Chick-fil-A", "dining", 9, 35),
    ("Olive Garden", "dining", 30, 110),
    ("Delta Air Lines", "travel", 180, 950),
    ("Marriott", "travel", 140, 620),
    ("Duke Energy", "utilities", 80, 260),
    ("Spectrum", "utilities", 60, 120),
    ("Verizon", "utilities", 55, 190),
    ("CVS Pharmacy", "health", 8, 90),
    ("Netflix", "entertainment", 15, 23),
    ("Spotify", "entertainment", 11, 17),
]


def money(x: float) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def rand_day(start: date, end: date) -> date:
    return start + timedelta(days=rng.randrange((end - start).days + 1))


def month_starts():
    d = START
    while d <= END:
        yield d
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def month_end(d: date) -> date:
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


customers, accounts, txns = [], [], []


def is_open(acc, day, closes) -> bool:
    return acc is not None and (acc not in closes or day < closes[acc])


def add_txn(account_id, day, amount, txn_type, merchant=None, category=None):
    txns.append([None, account_id, day, money(amount), txn_type, merchant, category])


for cid in range(1, 31):
    first, last = rng.choice(FIRST), rng.choice(LAST)
    branch = rng.choice(BRANCHES)
    segment = rng.choices(["retail", "premier", "small_business"], weights=[70, 20, 10])[0]
    joined = rand_day(date(2018, 1, 1), date(2025, 12, 31))
    customers.append(
        (
            cid,
            first,
            last,
            f"{first.lower()}.{last.lower()}{cid}@example.com",
            branch[2],
            branch[3],
            segment,
            branch[0],
            joined,
        )
    )

    pay = {"retail": (1400, 2600), "premier": (3800, 6500), "small_business": (2500, 9000)}[segment]
    paycheck = rng.uniform(*pay)
    housing = (rng.choice(["Rent", "Mortgage"]), 2 * paycheck * rng.uniform(0.30, 0.42))
    auto_loan = rng.uniform(280, 650) if rng.random() < 0.5 else None

    # every customer has checking; savings and a credit card are optional
    checking = len(accounts) + 1
    accounts.append([checking, cid, "checking", "open", joined, None, money(rng.uniform(500, 8000))])
    savings = card = None
    if rng.random() < 0.6:
        savings = len(accounts) + 1
        accounts.append(
            [savings, cid, "savings", "open", rand_day(joined, date(2026, 3, 1)), None, money(rng.uniform(1000, 40000))]
        )
    if rng.random() < 0.45:
        card = len(accounts) + 1
        accounts.append(
            [card, cid, "credit_card", "open", rand_day(joined, date(2026, 3, 1)), None, money(-rng.uniform(0, 1500))]
        )

    # a few accounts get closed partway through the period
    closes = {}
    for acc in (savings, card):
        if acc and rng.random() < 0.08:
            closes[acc] = rand_day(date(2026, 6, 1), date(2026, 8, 31))

    for m in month_starts():
        last_day = month_end(m)
        for day in (m, m + timedelta(days=14)):
            add_txn(checking, day, paycheck * rng.uniform(0.97, 1.03), "deposit", "Payroll", "income")
        add_txn(checking, m + timedelta(days=2), -housing[1], "transfer_out", housing[0], "housing")
        if auto_loan:
            add_txn(checking, m + timedelta(days=9), -auto_loan, "transfer_out", "Auto Loan", "loan")
        for _ in range(rng.randint(4, 9)):
            name, cat, lo, hi = rng.choice(MERCHANTS)
            add_txn(checking, rand_day(m, last_day), -rng.uniform(lo, hi), "card_purchase", name, cat)
        if segment == "retail" and rng.random() < 0.2:
            add_txn(checking, last_day, -12, "fee", None, "fees")
        if is_open(savings, last_day, closes):
            amount = rng.choice([150, 200, 300, 500, 800])
            day = m + timedelta(days=rng.randint(2, 6))
            add_txn(checking, day, -amount, "transfer_out", None, "transfer")
            add_txn(savings, day, amount, "transfer_in", None, "transfer")
            add_txn(savings, last_day, rng.uniform(4, 60), "interest", None, "interest")
        if is_open(card, last_day, closes):
            for _ in range(rng.randint(3, 8)):
                name, cat, lo, hi = rng.choice(MERCHANTS)
                add_txn(card, rand_day(m, last_day), -rng.uniform(lo, hi), "card_purchase", name, cat)
            payment = rng.uniform(150, 1200)
            day = m + timedelta(days=rng.randint(18, 25))
            add_txn(checking, day, -payment, "card_payment", None, "card payment")
            add_txn(card, day, payment, "card_payment", None, "card payment")

    for acc, closed_on in closes.items():
        row = accounts[acc - 1]
        row[3], row[5] = "closed", closed_on

# drop transactions dated after an account closed, then number them in date order
closed = {a[0]: a[5] for a in accounts if a[5]}
txns = [t for t in txns if t[1] not in closed or t[2] < closed[t[1]]]
txns.sort(key=lambda t: (t[2], t[1], t[4]))
for i, t in enumerate(txns, start=1):
    t[0] = i

# balances = opening balance + everything posted in the period
for acc in accounts:
    acc[6] = money(float(acc[6]) + float(sum(t[3] for t in txns if t[1] == acc[0])))
    if acc[3] == "closed":
        acc[6] = money(0)


def lit(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (int, Decimal)):
        return str(v)
    if isinstance(v, date):
        return f"'{v.isoformat()}'"
    return "'" + str(v).replace("'", "''") + "'"


def inserts(table: str, columns: list[str], rows: list, chunk: int = 250) -> str:
    parts = []
    for i in range(0, len(rows), chunk):
        values = ",\n".join("(" + ", ".join(lit(v) for v in row) + ")" for row in rows[i : i + chunk])
        parts.append(f"INSERT INTO {table} ({', '.join(columns)}) VALUES\n{values};\n")
    return "\n".join(parts)


sql = [
    "-- Generated by scripts/generate_seed.py. Made-up data for the demo; not real people or accounts.\n",
    inserts("branches", ["branch_id", "branch_name", "city", "state"], BRANCHES),
    inserts(
        "customers",
        ["customer_id", "first_name", "last_name", "email", "city", "state", "segment", "branch_id", "joined_on"],
        customers,
    ),
    inserts(
        "accounts",
        ["account_id", "customer_id", "account_type", "status", "opened_on", "closed_on", "balance"],
        accounts,
    ),
    inserts(
        "transactions",
        ["transaction_id", "account_id", "posted_on", "amount", "txn_type", "merchant", "category"],
        txns,
    ),
]
OUT.write_text("\n".join(sql), encoding="utf-8")
print(
    f"wrote {OUT.relative_to(OUT.parents[2])}: {len(customers)} customers, {len(accounts)} accounts, "
    f"{len(txns)} transactions"
)
