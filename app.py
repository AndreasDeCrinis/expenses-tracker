from flask import Flask, render_template, request, redirect, url_for
import csv
import os
from collections import defaultdict

app = Flask(__name__)

INCOME_CSV = "incomes.csv"
EXPENSE_CSV = "expenses.csv"


def migrate_expense_csv_if_needed():
    """Migrate existing expenses.csv to add frequency + split_mode if missing."""
    if not os.path.exists(EXPENSE_CSV):
        return

    with open(EXPENSE_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        # Already new format
        if "frequency" in fieldnames and "split_mode" in fieldnames:
            return

        rows = list(reader)

    new_rows = []
    for row in rows:
        category = row.get("category", "")
        person_or_account = row.get("person_or_account", "")
        description = row.get("description", "")
        is_shared = row.get("is_shared", "nein")

        if "frequency" in fieldnames:
            frequency = row.get("frequency", "monthly") or "monthly"
        else:
            frequency = "monthly"

        if "split_mode" in fieldnames:
            split_mode = row.get("split_mode", "income") or "income"
        else:
            split_mode = "income"  # Standard: gehaltsabhängig

        amount = row.get("amount", "0")

        new_rows.append({
            "category": category,
            "person_or_account": person_or_account,
            "description": description,
            "is_shared": is_shared,
            "frequency": frequency,
            "split_mode": split_mode,
            "amount": amount,
        })

    # Overwrite with new structure
    with open(EXPENSE_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "category", "person_or_account", "description",
            "is_shared", "frequency", "split_mode", "amount"
        ])
        for r in new_rows:
            writer.writerow([
                r["category"],
                r["person_or_account"],
                r["description"],
                r["is_shared"],
                r["frequency"],
                r["split_mode"],
                r["amount"],
            ])


def ensure_csv_files():
    """Create or migrate CSV files."""
    if not os.path.exists(INCOME_CSV):
        with open(INCOME_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["person", "source", "amount"])

    if not os.path.exists(EXPENSE_CSV):
        with open(EXPENSE_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "category", "person_or_account", "description",
                "is_shared", "frequency", "split_mode", "amount"
            ])
    else:
        migrate_expense_csv_if_needed()


def load_incomes():
    """Load all monthly income rows, skipping broken/empty ones."""
    incomes = []
    if not os.path.exists(INCOME_CSV):
        return incomes

    with open(INCOME_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                raw = row.get("amount")
                if raw is None or str(raw).strip() == "":
                    continue
                amount = float(str(raw).replace(",", "."))
                row["amount"] = amount
                incomes.append(row)
            except (ValueError, TypeError, KeyError):
                continue
    return incomes


def load_expenses():
    """Load all expense rows, compute monthly equivalents, skip broken/empty ones."""
    expenses = []
    if not os.path.exists(EXPENSE_CSV):
        return expenses

    with open(EXPENSE_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        for row in reader:
            try:
                raw = row.get("amount")
                if raw is None or str(raw).strip() == "":
                    continue
                amount = float(str(raw).replace(",", "."))
                row["amount"] = amount

                # frequency
                freq_raw = row.get("frequency") if "frequency" in fieldnames else None
                freq = (freq_raw or "monthly").strip().lower()
                if freq not in ("monthly", "quarterly", "yearly"):
                    freq = "monthly"
                row["frequency"] = freq

                # split mode: income (gehaltsabhängig) oder equal (50:50)
                mode_raw = row.get("split_mode") if "split_mode" in fieldnames else None
                split_mode = (mode_raw or "income").strip().lower()
                if split_mode not in ("income", "equal"):
                    split_mode = "income"
                row["split_mode"] = split_mode

                # monatliches Äquivalent
                if freq == "yearly":
                    monthly_amount = amount / 12.0
                elif freq == "quarterly":
                    monthly_amount = amount / 3.0
                else:
                    monthly_amount = amount

                row["monthly_amount"] = monthly_amount
                expenses.append(row)
            except (ValueError, TypeError, KeyError):
                continue
    return expenses


def save_incomes(incomes):
    """Overwrite incomes.csv with the provided list of income dicts."""
    with open(INCOME_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["person", "source", "amount"])
        for row in incomes:
            writer.writerow([
                row.get("person", ""),
                row.get("source", ""),
                row.get("amount", 0),
            ])


def save_expenses(expenses):
    """Overwrite expenses.csv with the provided list of expense dicts."""
    with open(EXPENSE_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "category", "person_or_account", "description",
            "is_shared", "frequency", "split_mode", "amount"
        ])
        for row in expenses:
            writer.writerow([
                row.get("category", ""),
                row.get("person_or_account", ""),
                row.get("description", ""),
                row.get("is_shared", "nein"),
                row.get("frequency", "monthly"),
                row.get("split_mode", "income"),
                row.get("amount", 0),
            ])


def group_sum(records, key_field: str):
    """Group by key_field and sum the 'amount' field."""
    summary = {}
    for r in records:
        key = r.get(key_field, "Unbekannt") or "Unbekannt"
        amount = r.get("amount", 0) or 0
        summary[key] = summary.get(key, 0) + amount
    return summary


@app.route("/")
def index():
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    ensure_csv_files()

    incomes = load_incomes()
    expenses = load_expenses()

    total_income = sum(i["amount"] for i in incomes)
    total_expense = sum(e["monthly_amount"] for e in expenses)
    remaining = total_income - total_expense

    income_by_person = group_sum(incomes, "person")

    # Ausgaben für das Diagramm: monatliche Beträge pro Kategorie
    expenses_for_chart = []
    for e in expenses:
        clone = dict(e)
        clone["amount"] = e.get("monthly_amount", e.get("amount", 0))
        expenses_for_chart.append(clone)
    expense_by_category = group_sum(expenses_for_chart, "category")

    # Gemeinsame Ausgaben (flag is_shared == "ja")
    shared_expenses_total = sum(
        e["monthly_amount"] for e in expenses if e.get("is_shared") == "ja"
    )

    # Einkommen von Andreas & Katharina
    andreas_income = sum(i["amount"] for i in incomes if i.get("person") == "Andreas")
    katharina_income = sum(i["amount"] for i in incomes if i.get("person") == "Katharina")
    income_two = andreas_income + katharina_income

    # Kindergeld (oder andere explizite Familien-Einnahmen, die keiner Person zugeordnet werden)
    extra_family_income = sum(
        i["amount"] for i in incomes if i.get("person") == "Kindergeld Anton"
    )

    # Netto-gemeinsame Kosten nach Abzug Kindergeld
    net_shared = max(shared_expenses_total - extra_family_income, 0.0)

    # Wie stark werden die einzelnen gemeinsamen Ausgaben durch Kindergeld "entlastet"?
    if shared_expenses_total > 0:
        reduction_factor = net_shared / shared_expenses_total
    else:
        reduction_factor = 0.0

    # Aufteilung nach 50:50 bzw. gehaltsabhängig, pro Konto
    andreas_by_account = defaultdict(float)
    katharina_by_account = defaultdict(float)

    andreas_equal_total = 0.0
    katharina_equal_total = 0.0
    andreas_income_total = 0.0
    katharina_income_total = 0.0

    equal_shared_before = sum(
        e["monthly_amount"]
        for e in expenses
        if e.get("is_shared") == "ja" and e.get("split_mode") == "equal"
    )
    income_shared_before = sum(
        e["monthly_amount"]
        for e in expenses
        if e.get("is_shared") == "ja" and e.get("split_mode") == "income"
    )

    equal_shared = equal_shared_before * reduction_factor
    income_shared = income_shared_before * reduction_factor

    for e in expenses:
        if e.get("is_shared") != "ja":
            continue

        base = e["monthly_amount"] * reduction_factor
        if base <= 0:
            continue

        account = e.get("person_or_account") or "Unbekanntes Konto"
        mode = e.get("split_mode", "income")

        if income_two <= 0:
            # Fallback: wenn kein Einkommen hinterlegt → 50:50
            mode = "equal"

        if mode == "equal":
            a_share = base / 2.0
            k_share = base / 2.0
            andreas_equal_total += a_share
            katharina_equal_total += k_share
        else:  # gehaltsabhängig
            a_share = base * (andreas_income / income_two) if income_two > 0 else base / 2.0
            k_share = base * (katharina_income / income_two) if income_two > 0 else base / 2.0
            andreas_income_total += a_share
            katharina_income_total += k_share

        andreas_by_account[account] += a_share
        katharina_by_account[account] += k_share

    andreas_share_total = andreas_equal_total + andreas_income_total
    katharina_share_total = katharina_equal_total + katharina_income_total

    # Übersicht: wer überweist wieviel auf welches Konto
    accounts = sorted(set(andreas_by_account.keys()) | set(katharina_by_account.keys()))
    transfer_overview = []
    for acc in accounts:
        a = andreas_by_account.get(acc, 0.0)
        k = katharina_by_account.get(acc, 0.0)
        transfer_overview.append({
            "account": acc,
            "andreas": a,
            "katharina": k,
            "total": a + k,
        })

    return render_template(
        "dashboard.html",
        incomes=incomes,
        expenses=expenses,
        total_income=total_income,
        total_expense=total_expense,
        remaining=remaining,
        income_by_person=income_by_person,
        expense_by_category=expense_by_category,
        shared_expenses=shared_expenses_total,
        equal_shared=equal_shared,
        income_shared=income_shared,
        extra_family_income=extra_family_income,
        net_shared=net_shared,
        andreas_income=andreas_income,
        katharina_income=katharina_income,
        andreas_share_equal=andreas_equal_total,
        katharina_share_equal=katharina_equal_total,
        andreas_share_income=andreas_income_total,
        katharina_share_income=katharina_income_total,
        andreas_share_total=andreas_share_total,
        katharina_share_total=katharina_share_total,
        transfer_overview=transfer_overview,
    )


@app.route("/add_income", methods=["GET", "POST"])
def add_income():
    ensure_csv_files()

    if request.method == "POST":
        person = request.form.get("person")
        source = request.form.get("source")
        amount_raw = request.form.get("amount") or "0"
        amount = float(str(amount_raw).replace(",", "."))

        with open(INCOME_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([person, source, amount])

        return redirect(url_for("dashboard"))

    return render_template("add_income.html")


@app.route("/add_expense", methods=["GET", "POST"])
def add_expense():
    ensure_csv_files()

    if request.method == "POST":
        category = request.form.get("category") or ""
        category_custom = (request.form.get("category_custom") or "").strip()
        if category_custom:
            category = category_custom
        if not category:
            category = "Unkategorisiert"

        person_or_account = request.form.get("person_or_account")
        description = request.form.get("description")

        is_shared = "ja" if request.form.get("is_shared") == "on" else "nein"

        frequency = (request.form.get("frequency") or "monthly").strip().lower()
        if frequency not in ("monthly", "quarterly", "yearly"):
            frequency = "monthly"

        split_mode = (request.form.get("split_mode") or "income").strip().lower()
        if split_mode not in ("income", "equal"):
            split_mode = "income"

        amount_raw = request.form.get("amount") or "0"
        amount = float(str(amount_raw).replace(",", "."))

        with open(EXPENSE_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                category, person_or_account, description,
                is_shared, frequency, split_mode, amount
            ])

        return redirect(url_for("dashboard"))

    return render_template("add_expense.html")


@app.route("/edit_income/<int:index>", methods=["GET", "POST"])
def edit_income(index):
    """Edit an existing income entry by its index in the list."""
    ensure_csv_files()
    incomes = load_incomes()

    if index < 0 or index >= len(incomes):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        person = request.form.get("person")
        source = request.form.get("source")
        amount_raw = request.form.get("amount") or "0"
        amount = float(str(amount_raw).replace(",", "."))

        incomes[index]["person"] = person
        incomes[index]["source"] = source
        incomes[index]["amount"] = amount

        save_incomes(incomes)
        return redirect(url_for("dashboard"))

    income = incomes[index]
    return render_template("edit_income.html", income=income, index=index)


@app.route("/edit_expense/<int:index>", methods=["GET", "POST"])
def edit_expense(index):
    """Edit an existing expense entry by its index in the list."""
    ensure_csv_files()
    expenses = load_expenses()

    if index < 0 or index >= len(expenses):
        return redirect(url_for("dashboard"))

    base_categories = [
        "Hypothek / Miete",
        "Strom",
        "Auto",
        "Versicherung",
        "Persönliche Versicherung",
        "Persönliches Handy",
        "Kinderbetreuung",
        "Lebensmittel",
        "Sonstige feste Kosten",
        "Sonstige variable Kosten",
    ]

    if request.method == "POST":
        category = request.form.get("category") or ""
        category_custom = (request.form.get("category_custom") or "").strip()
        if category_custom:
            category = category_custom
        if not category:
            category = "Unkategorisiert"

        person_or_account = request.form.get("person_or_account")
        description = request.form.get("description")
        is_shared = "ja" if request.form.get("is_shared") == "on" else "nein"

        frequency = (request.form.get("frequency") or "monthly").strip().lower()
        if frequency not in ("monthly", "quarterly", "yearly"):
            frequency = "monthly"

        split_mode = (request.form.get("split_mode") or "income").strip().lower()
        if split_mode not in ("income", "equal"):
            split_mode = "income"

        amount_raw = request.form.get("amount") or "0"
        amount = float(str(amount_raw).replace(",", "."))

        expenses[index]["category"] = category
        expenses[index]["person_or_account"] = person_or_account
        expenses[index]["description"] = description
        expenses[index]["is_shared"] = is_shared
        expenses[index]["frequency"] = frequency
        expenses[index]["split_mode"] = split_mode
        expenses[index]["amount"] = amount

        save_expenses(expenses)
        return redirect(url_for("dashboard"))

    expense = expenses[index]

    return render_template(
        "edit_expense.html",
        expense=expense,
        index=index,
        base_categories=base_categories,
    )


if __name__ == "__main__":
    ensure_csv_files()
    app.run(host="0.0.0.0", port=8080, debug=True)
