from flask import Flask, render_template, request, redirect, url_for
import csv
import os

app = Flask(__name__)

INCOME_CSV = "incomes.csv"
EXPENSE_CSV = "expenses.csv"


def ensure_csv_files():
    """Create CSV files with headers if they do not exist yet."""
    if not os.path.exists(INCOME_CSV):
        with open(INCOME_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # person = Andreas, Katharina, Großmutter, Kindergeld, ...
            writer.writerow(["person", "source", "amount"])

    if not os.path.exists(EXPENSE_CSV):
        with open(EXPENSE_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # frequency = monthly / quarterly / yearly
            writer.writerow(
                ["category", "person_or_account", "description", "is_shared", "frequency", "amount"]
            )


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

                # frequency support, backward compatible
                if "frequency" in fieldnames:
                    freq_raw = row.get("frequency")
                else:
                    freq_raw = None

                freq = (freq_raw or "monthly").strip().lower()
                if freq not in ("monthly", "quarterly", "yearly"):
                    freq = "monthly"

                row["frequency"] = freq

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
        writer.writerow(["category", "person_or_account", "description", "is_shared", "frequency", "amount"])
        for row in expenses:
            writer.writerow([
                row.get("category", ""),
                row.get("person_or_account", ""),
                row.get("description", ""),
                row.get("is_shared", "nein"),
                row.get("frequency", "monthly"),
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

    # Use monthly equivalent for totals
    total_income = sum(i["amount"] for i in incomes)
    total_expense = sum(e["monthly_amount"] for e in expenses)
    remaining = total_income - total_expense

    income_by_person = group_sum(incomes, "person")

    # For category chart we want monthly totals per category
    expenses_for_chart = []
    for e in expenses:
        clone = dict(e)
        clone["amount"] = e.get("monthly_amount", e.get("amount", 0))
        expenses_for_chart.append(clone)
    expense_by_category = group_sum(expenses_for_chart, "category")

    # Gemeinsame Fixkosten = monatlich äquivalente Summe aller is_shared == "ja"
    shared_expenses = sum(e["monthly_amount"] for e in expenses if e.get("is_shared") == "ja")

    # Einnahmen von Andreas und Katharina
    andreas_income = sum(i["amount"] for i in incomes if i.get("person") == "Andreas")
    katharina_income = sum(i["amount"] for i in incomes if i.get("person") == "Katharina")
    income_two = andreas_income + katharina_income

    # Alle anderen Einnahmen (z.B. Kindergeld, Großeltern) reduzieren zuerst die gemeinsamen Fixkosten
    extra_family_income = total_income - income_two
    cost_to_split = max(shared_expenses - extra_family_income, 0.0)

    andreas_share = None
    katharina_share = None
    if income_two > 0 and cost_to_split > 0:
        andreas_share = cost_to_split * (andreas_income / income_two)
        katharina_share = cost_to_split * (katharina_income / income_two)

    return render_template(
        "dashboard.html",
        incomes=incomes,
        expenses=expenses,
        total_income=total_income,
        total_expense=total_expense,
        remaining=remaining,
        income_by_person=income_by_person,
        expense_by_category=expense_by_category,
        shared_expenses=shared_expenses,
        extra_family_income=extra_family_income,
        cost_to_split=cost_to_split,
        andreas_income=andreas_income,
        katharina_income=katharina_income,
        andreas_share=andreas_share,
        katharina_share=katharina_share,
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

        amount_raw = request.form.get("amount") or "0"
        amount = float(str(amount_raw).replace(",", "."))

        with open(EXPENSE_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([category, person_or_account, description, is_shared, frequency, amount])

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

        amount_raw = request.form.get("amount") or "0"
        amount = float(str(amount_raw).replace(",", "."))

        expenses[index]["category"] = category
        expenses[index]["person_or_account"] = person_or_account
        expenses[index]["description"] = description
        expenses[index]["is_shared"] = is_shared
        expenses[index]["frequency"] = frequency
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
