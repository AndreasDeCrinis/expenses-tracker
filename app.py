from flask import Flask, render_template, request, redirect, url_for
import csv
import os
from collections import defaultdict

app = Flask(__name__)

# -------------------------------------------------------------------
# Paths (alles in data/ Unterordner)
# -------------------------------------------------------------------
DATA_DIR = "data"
INCOME_CSV = os.path.join(DATA_DIR, "incomes.csv")
EXPENSE_CSV = os.path.join(DATA_DIR, "expenses.csv")
ACCOUNTS_CSV = os.path.join(DATA_DIR, "accounts.csv")


# -------------------------------------------------------------------
# Helpers: Ordner & Migration
# -------------------------------------------------------------------
def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def migrate_old_csvs():
    """
    Falls alte incomes.csv / expenses.csv im Projekt-Root existieren,
    verschiebe sie einmalig in den data/ Ordner.
    """
    old_incomes = "incomes.csv"
    old_expenses = "expenses.csv"

    if os.path.exists(old_incomes) and not os.path.exists(INCOME_CSV):
        os.rename(old_incomes, INCOME_CSV)

    if os.path.exists(old_expenses) and not os.path.exists(EXPENSE_CSV):
        os.rename(old_expenses, EXPENSE_CSV)


def migrate_income_csv_if_needed():
    """Sorge dafür, dass incomes.csv eine 'account'-Spalte hat."""
    if not os.path.exists(INCOME_CSV):
        return

    with open(INCOME_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        if "account" in fieldnames:
            return  # schon im neuen Format

        rows = list(reader)

    # altes Format: person, source, amount → erweitern um account
    with open(INCOME_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["person", "source", "amount", "account"])
        for r in rows:
            writer.writerow([
                r.get("person", ""),
                r.get("source", ""),
                r.get("amount", "0"),
                "",  # account leer
            ])


def migrate_expense_csv_if_needed():
    """
    Sorge dafür, dass expenses.csv die Spalten
    frequency, split_mode, paid_from_account hat (rückwärtskompatibel).
    """
    if not os.path.exists(EXPENSE_CSV):
        return

    with open(EXPENSE_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        has_frequency = "frequency" in fieldnames
        has_split_mode = "split_mode" in fieldnames
        has_paid_from = "paid_from_account" in fieldnames

        # schon vollständiges Schema
        if has_frequency and has_split_mode and has_paid_from:
            return

        rows = list(reader)

    new_rows = []
    for row in rows:
        category = row.get("category", "")
        person_or_account = row.get("person_or_account", "")
        description = row.get("description", "")
        is_shared = row.get("is_shared", "nein")

        if has_frequency:
            frequency = (row.get("frequency") or "monthly").strip().lower()
        else:
            frequency = "monthly"

        if has_split_mode:
            split_mode = (row.get("split_mode") or "income").strip().lower()
        else:
            split_mode = "income"

        if has_paid_from:
            paid_from_account = row.get("paid_from_account") or person_or_account
        else:
            paid_from_account = person_or_account

        amount = row.get("amount", "0")

        new_rows.append({
            "category": category,
            "person_or_account": person_or_account,
            "description": description,
            "is_shared": is_shared,
            "frequency": frequency,
            "split_mode": split_mode,
            "amount": amount,
            "paid_from_account": paid_from_account,
        })

    with open(EXPENSE_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "category", "person_or_account", "description",
            "is_shared", "frequency", "split_mode", "amount",
            "paid_from_account",
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
                r["paid_from_account"],
            ])


def ensure_accounts_file():
    """Erzeuge accounts.csv mit Standardkonten, falls noch nicht vorhanden."""
    if os.path.exists(ACCOUNTS_CSV):
        return

    default_accounts = [
        "Gemeinsames Fixkosten-Konto",
        "Gemeinsames Lebensmittel-Konto",
        "Andreas Konto",
        "Katharina Konto",
        "Sonstiges Konto",
    ]
    with open(ACCOUNTS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name"])
        for acc in default_accounts:
            writer.writerow([acc])


def ensure_csv_files():
    """Initialisiere alle CSVs & führe Migrationen aus."""
    ensure_data_dir()
    migrate_old_csvs()

    # incomes
    if not os.path.exists(INCOME_CSV):
        with open(INCOME_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["person", "source", "amount", "account"])
    else:
        migrate_income_csv_if_needed()

    # expenses
    if not os.path.exists(EXPENSE_CSV):
        with open(EXPENSE_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "category", "person_or_account", "description",
                "is_shared", "frequency", "split_mode", "amount",
                "paid_from_account",
            ])
    else:
        migrate_expense_csv_if_needed()

    # accounts
    ensure_accounts_file()


# -------------------------------------------------------------------
# Laden / Speichern: Accounts
# -------------------------------------------------------------------
def load_accounts():
    if not os.path.exists(ACCOUNTS_CSV):
        return []
    accounts = []
    with open(ACCOUNTS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("name") or "").strip()
            if name:
                accounts.append(name)
    return accounts


def append_account(name: str):
    name = (name or "").strip()
    if not name:
        return
    accounts = load_accounts()
    if name in accounts:
        return
    with open(ACCOUNTS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([name])


# -------------------------------------------------------------------
# Laden / Speichern: Incomes & Expenses
# -------------------------------------------------------------------
def load_incomes():
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
                row["account"] = row.get("account", "")
                incomes.append(row)
            except (ValueError, TypeError, KeyError):
                continue
    return incomes


def load_expenses():
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

                freq_raw = row.get("frequency") if "frequency" in fieldnames else None
                freq = (freq_raw or "monthly").strip().lower()
                if freq not in ("monthly", "quarterly", "yearly"):
                    freq = "monthly"
                row["frequency"] = freq

                mode_raw = row.get("split_mode") if "split_mode" in fieldnames else None
                split_mode = (mode_raw or "income").strip().lower()
                if split_mode not in ("income", "equal"):
                    split_mode = "income"
                row["split_mode"] = split_mode

                paid_from = row.get("paid_from_account") if "paid_from_account" in fieldnames else None
                row["paid_from_account"] = paid_from or row.get("person_or_account", "")

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
    with open(INCOME_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["person", "source", "amount", "account"])
        for row in incomes:
            writer.writerow([
                row.get("person", ""),
                row.get("source", ""),
                row.get("amount", 0),
                row.get("account", ""),
            ])


def save_expenses(expenses):
    with open(EXPENSE_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "category", "person_or_account", "description",
            "is_shared", "frequency", "split_mode", "amount",
            "paid_from_account",
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
                row.get("paid_from_account", ""),
            ])


def group_sum(records, key_field: str):
    summary = {}
    for r in records:
        key = r.get(key_field, "Unbekannt") or "Unbekannt"
        amount = r.get("amount", 0) or 0
        summary[key] = summary.get(key, 0) + amount
    return summary


# -------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------
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

    # Ausgaben für Charts: nach Kategorie
    expenses_for_chart = []
    for e in expenses:
        clone = dict(e)
        clone["amount"] = e.get("monthly_amount", e.get("amount", 0))
        expenses_for_chart.append(clone)
    expense_by_category = group_sum(expenses_for_chart, "category")

    # Gemeinsame Ausgaben
    shared_expenses_total = sum(
        e["monthly_amount"] for e in expenses if e.get("is_shared") == "ja"
    )

    # Einkommen Andreas & Katharina
    andreas_income = sum(i["amount"] for i in incomes if i.get("person") == "Andreas")
    katharina_income = sum(i["amount"] for i in incomes if i.get("person") == "Katharina")
    income_two = andreas_income + katharina_income

    # Kindergeld & Co.
    extra_family_income = sum(
        i["amount"] for i in incomes if i.get("person") == "Kindergeld Anton"
    )

    net_shared = max(shared_expenses_total - extra_family_income, 0.0)

    if shared_expenses_total > 0:
        reduction_factor = net_shared / shared_expenses_total
    else:
        reduction_factor = 0.0

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

        account = e.get("paid_from_account") or e.get("person_or_account") or "Unbekanntes Konto"
        mode = e.get("split_mode", "income")

        if income_two <= 0:
            mode = "equal"

        if mode == "equal":
            a_share = base / 2.0
            k_share = base / 2.0
            andreas_equal_total += a_share
            katharina_equal_total += k_share
        else:
            a_share = base * (andreas_income / income_two) if income_two > 0 else base / 2.0
            k_share = base * (katharina_income / income_two) if income_two > 0 else base / 2.0
            andreas_income_total += a_share
            katharina_income_total += k_share

        andreas_by_account[account] += a_share
        katharina_by_account[account] += k_share

    andreas_share_total = andreas_equal_total + andreas_income_total
    katharina_share_total = katharina_equal_total + katharina_income_total

    # Überweisungsübersicht
    accounts_list = sorted(set(andreas_by_account.keys()) | set(katharina_by_account.keys()))
    transfer_overview = []
    for acc in accounts_list:
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


@app.route("/accounts", methods=["GET", "POST"])
def accounts():
    ensure_csv_files()
    if request.method == "POST":
        name = request.form.get("name")
        append_account(name)
        return redirect(url_for("accounts"))

    accounts_list = load_accounts()
    return render_template("accounts.html", accounts=accounts_list)


@app.route("/accounts/edit/<int:index>", methods=["GET", "POST"])
def edit_account(index):
    ensure_csv_files()

    accounts = load_accounts()
    if index < 0 or index >= len(accounts):
        return redirect(url_for("accounts"))

    old_name = accounts[index]

    if request.method == "POST":
        new_name = (request.form.get("name") or "").strip()
        if new_name and new_name != old_name:

            # 1. Accounts-Datei aktualisieren
            accounts[index] = new_name
            with open(ACCOUNTS_CSV, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["name"])
                for a in accounts:
                    writer.writerow([a])

            # 2. Einnahmen aktualisieren
            incomes = load_incomes()
            changed = False
            for inc in incomes:
                if inc.get("account") == old_name:
                    inc["account"] = new_name
                    changed = True
            if changed:
                save_incomes(incomes)

            # 3. Ausgaben aktualisieren
            expenses = load_expenses()
            changed = False
            for exp in expenses:
                if exp.get("paid_from_account") == old_name:
                    exp["paid_from_account"] = new_name
                    changed = True
            if changed:
                save_expenses(expenses)

        return redirect(url_for("accounts"))

    return render_template("edit_account.html", index=index, old_name=old_name)


@app.route("/add_income", methods=["GET", "POST"])
def add_income():
    ensure_csv_files()
    accounts_list = load_accounts()

    if request.method == "POST":
        person = request.form.get("person")
        source = request.form.get("source")
        amount_raw = request.form.get("amount") or "0"
        amount = float(str(amount_raw).replace(",", "."))
        account = request.form.get("income_account") or ""

        with open(INCOME_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([person, source, amount, account])

        return redirect(url_for("dashboard"))

    return render_template("add_income.html", accounts=accounts_list)


@app.route("/add_expense", methods=["GET", "POST"])
def add_expense():
    ensure_csv_files()
    accounts_list = load_accounts()

    if request.method == "POST":
        category = request.form.get("category") or ""
        category_custom = (request.form.get("category_custom") or "").strip()
        if category_custom:
            category = category_custom
        if not category:
            category = "Unkategorisiert"

        person_or_account = request.form.get("person_or_account")
        paid_from_account = request.form.get("paid_from_account")
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
                is_shared, frequency, split_mode, amount,
                paid_from_account,
            ])

        return redirect(url_for("dashboard"))

    return render_template("add_expense.html", accounts=accounts_list)


@app.route("/edit_income/<int:index>", methods=["GET", "POST"])
def edit_income(index):
    ensure_csv_files()
    incomes = load_incomes()
    accounts_list = load_accounts()

    if index < 0 or index >= len(incomes):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        person = request.form.get("person")
        source = request.form.get("source")
        amount_raw = request.form.get("amount") or "0"
        amount = float(str(amount_raw).replace(",", "."))

        account = request.form.get("income_account") or ""

        incomes[index]["person"] = person
        incomes[index]["source"] = source
        incomes[index]["amount"] = amount
        incomes[index]["account"] = account

        save_incomes(incomes)
        return redirect(url_for("dashboard"))

    income = incomes[index]
    return render_template("edit_income.html", income=income, index=index, accounts=accounts_list)


@app.route("/edit_expense/<int:index>", methods=["GET", "POST"])
def edit_expense(index):
    ensure_csv_files()
    expenses = load_expenses()
    accounts_list = load_accounts()

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
        paid_from_account = request.form.get("paid_from_account")
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
        expenses[index]["paid_from_account"] = paid_from_account
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
        accounts=accounts_list,
    )


if __name__ == "__main__":
    ensure_csv_files()
    app.run(host="0.0.0.0", port=8080, debug=True)
