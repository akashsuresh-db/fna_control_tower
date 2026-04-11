# Databricks notebook source
# MAGIC %md
# MAGIC # Finance & Accounting Demo - Setup & Data Generation
# MAGIC
# MAGIC This notebook generates all synthetic datasets for P2P, O2C, and R2R workflows.
# MAGIC Covers: Vendors, POs, GRNs, Invoices, Customers, Sales Orders, GL, Journal Entries
# MAGIC
# MAGIC **Catalog**: hp_sf_test
# MAGIC **Schema**: finance_and_accounting

# COMMAND ----------

# MAGIC %md ## Configuration

# COMMAND ----------

dbutils.widgets.text("catalog", "hp_sf_test", "Unity Catalog")
dbutils.widgets.text("schema", "finance_and_accounting", "Schema")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_invoices"

spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"USE SCHEMA {SCHEMA}")

# Create volume for raw invoice files
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_invoices")

print(f"Using: {CATALOG}.{SCHEMA}")
print(f"Volume: {VOLUME_PATH}")

# COMMAND ----------

# MAGIC %md ## Install Dependencies

# COMMAND ----------

# MAGIC %pip install faker

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_invoices"

# COMMAND ----------

# MAGIC %md ## Data Generation

# COMMAND ----------

import random
import json
import os
from datetime import date, timedelta, datetime
from decimal import Decimal, ROUND_HALF_UP
from faker import Faker
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import *

fake = Faker('en_IN')  # Indian locale for GST realism
random.seed(42)
Faker.seed(42)

spark = SparkSession.builder.getOrCreate()

# COMMAND ----------

# MAGIC %md ### Dimension: Vendors

# COMMAND ----------

VENDOR_COUNT = 100
CUSTOMER_COUNT = 150
PO_COUNT = 500
SO_COUNT = 600
INVOICE_COUNT = 550  # slightly more than POs to create orphan invoices
GRN_COUNT = 480      # fewer than POs to create 3-way match gaps

def random_date(start_days_ago=730, end_days_ago=0):
    start = date.today() - timedelta(days=start_days_ago)
    end = date.today() - timedelta(days=end_days_ago)
    return start + timedelta(days=random.randint(0, (end - start).days))

def random_gstin():
    states = ["27", "29", "06", "07", "09", "33", "36", "19", "08", "24"]
    state = random.choice(states)
    pan = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=5)) + \
          ''.join(random.choices('0123456789', k=4)) + \
          random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    return f"{state}{pan}1Z{random.choice('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')}"

vendor_categories = ["IT Services", "Manufacturing", "Logistics", "Consulting", "Raw Materials",
                     "Office Supplies", "Facilities", "Marketing", "Legal", "HR Services"]
payment_terms_options = ["NET30", "NET45", "NET60", "NET15", "COD", "NET90"]
currency_options = ["INR", "USD", "EUR", "GBP"]

vendors = []
for i in range(1, VENDOR_COUNT + 1):
    country = random.choices(["India", "USA", "UK", "Germany"], weights=[70, 15, 10, 5])[0]
    currency = "INR" if country == "India" else random.choice(["USD", "EUR", "GBP"])
    vendors.append({
        "vendor_id": f"VND{i:04d}",
        "vendor_name": fake.company(),
        "vendor_category": random.choice(vendor_categories),
        "contact_email": fake.company_email(),
        "contact_phone": fake.phone_number(),
        "address_line1": fake.street_address(),
        "city": fake.city(),
        "state": fake.state(),
        "country": country,
        "pincode": fake.postcode(),
        "gstin": random_gstin() if country == "India" else "",
        "pan": ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=5)) + ''.join(random.choices('0123456789', k=4)) + random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ') if country == "India" else "",
        "payment_terms": random.choice(payment_terms_options),
        "currency": currency,
        "bank_account": fake.bban(),
        "bank_ifsc": f"{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))}0{random.randint(100000,999999)}" if country == "India" else "",
        "is_active": random.choices([True, False], weights=[95, 5])[0],
        "created_date": str(random_date(1000, 400)),
        "modified_date": str(random_date(400, 0)),
        "_ingested_at": str(datetime.now()),
        "_source_system": "ERP_SAP"
    })

vendor_df = spark.createDataFrame(vendors)
vendor_df.write.format("delta").mode("overwrite").option("mergeSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.bronze_vendors")
print(f"Vendors: {vendor_df.count()} rows")

# COMMAND ----------

# MAGIC %md ### Dimension: Customers

# COMMAND ----------

customer_segments = ["Enterprise", "Mid-Market", "SMB", "Startup", "Government", "Non-Profit"]
industry_options = ["Technology", "Healthcare", "Retail", "BFSI", "Manufacturing", "Education", "Telecom"]

customers = []
for i in range(1, CUSTOMER_COUNT + 1):
    country = random.choices(["India", "USA", "UK", "Singapore"], weights=[65, 20, 10, 5])[0]
    customers.append({
        "customer_id": f"CUS{i:04d}",
        "customer_name": fake.company(),
        "segment": random.choice(customer_segments),
        "industry": random.choice(industry_options),
        "contact_email": fake.company_email(),
        "contact_phone": fake.phone_number(),
        "billing_address": fake.address().replace("\n", ", "),
        "city": fake.city(),
        "state": fake.state(),
        "country": country,
        "gstin": random_gstin() if country == "India" else "",
        "credit_limit": float(random.choice([500000, 1000000, 2000000, 5000000, 10000000])),
        "payment_terms": random.choice(payment_terms_options),
        "currency": "INR" if country == "India" else "USD",
        "account_manager": fake.name(),
        "is_active": random.choices([True, False], weights=[92, 8])[0],
        "created_date": str(random_date(1000, 300)),
        "modified_date": str(random_date(300, 0)),
        "_ingested_at": str(datetime.now()),
        "_source_system": "CRM_SALESFORCE"
    })

customer_df = spark.createDataFrame(customers)
customer_df.write.format("delta").mode("overwrite").option("mergeSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.bronze_customers")
print(f"Customers: {customer_df.count()} rows")

# COMMAND ----------

# MAGIC %md ### Chart of Accounts & Cost Centers

# COMMAND ----------

chart_of_accounts = [
    # Assets
    {"account_code": "1000", "account_name": "Cash and Cash Equivalents", "account_type": "Asset", "account_subtype": "Current Asset", "is_active": True},
    {"account_code": "1100", "account_name": "Accounts Receivable", "account_type": "Asset", "account_subtype": "Current Asset", "is_active": True},
    {"account_code": "1200", "account_name": "Inventory", "account_type": "Asset", "account_subtype": "Current Asset", "is_active": True},
    {"account_code": "1300", "account_name": "Prepaid Expenses", "account_type": "Asset", "account_subtype": "Current Asset", "is_active": True},
    {"account_code": "1500", "account_name": "Property Plant Equipment", "account_type": "Asset", "account_subtype": "Fixed Asset", "is_active": True},
    {"account_code": "1600", "account_name": "Accumulated Depreciation", "account_type": "Asset", "account_subtype": "Fixed Asset", "is_active": True},
    # Liabilities
    {"account_code": "2000", "account_name": "Accounts Payable", "account_type": "Liability", "account_subtype": "Current Liability", "is_active": True},
    {"account_code": "2100", "account_name": "Accrued Expenses", "account_type": "Liability", "account_subtype": "Current Liability", "is_active": True},
    {"account_code": "2200", "account_name": "Short Term Debt", "account_type": "Liability", "account_subtype": "Current Liability", "is_active": True},
    {"account_code": "2500", "account_name": "Long Term Debt", "account_type": "Liability", "account_subtype": "Non-Current Liability", "is_active": True},
    {"account_code": "2600", "account_name": "GST Payable", "account_type": "Liability", "account_subtype": "Tax Liability", "is_active": True},
    # Equity
    {"account_code": "3000", "account_name": "Share Capital", "account_type": "Equity", "account_subtype": "Equity", "is_active": True},
    {"account_code": "3100", "account_name": "Retained Earnings", "account_type": "Equity", "account_subtype": "Equity", "is_active": True},
    # Revenue
    {"account_code": "4000", "account_name": "Product Revenue", "account_type": "Revenue", "account_subtype": "Operating Revenue", "is_active": True},
    {"account_code": "4100", "account_name": "Service Revenue", "account_type": "Revenue", "account_subtype": "Operating Revenue", "is_active": True},
    {"account_code": "4200", "account_name": "Other Income", "account_type": "Revenue", "account_subtype": "Non-Operating Revenue", "is_active": True},
    # Expenses
    {"account_code": "5000", "account_name": "Cost of Goods Sold", "account_type": "Expense", "account_subtype": "COGS", "is_active": True},
    {"account_code": "5100", "account_name": "Salaries and Wages", "account_type": "Expense", "account_subtype": "Operating Expense", "is_active": True},
    {"account_code": "5200", "account_name": "Rent Expense", "account_type": "Expense", "account_subtype": "Operating Expense", "is_active": True},
    {"account_code": "5300", "account_name": "Utilities Expense", "account_type": "Expense", "account_subtype": "Operating Expense", "is_active": True},
    {"account_code": "5400", "account_name": "Marketing Expense", "account_type": "Expense", "account_subtype": "Operating Expense", "is_active": True},
    {"account_code": "5500", "account_name": "IT Expense", "account_type": "Expense", "account_subtype": "Operating Expense", "is_active": True},
    {"account_code": "5600", "account_name": "Travel Expense", "account_type": "Expense", "account_subtype": "Operating Expense", "is_active": True},
    {"account_code": "5700", "account_name": "Depreciation Expense", "account_type": "Expense", "account_subtype": "Non-Cash Expense", "is_active": True},
    {"account_code": "5800", "account_name": "Professional Fees", "account_type": "Expense", "account_subtype": "Operating Expense", "is_active": True},
    {"account_code": "5900", "account_name": "Interest Expense", "account_type": "Expense", "account_subtype": "Finance Cost", "is_active": True},
    {"account_code": "6000", "account_name": "Input GST", "account_type": "Expense", "account_subtype": "Tax", "is_active": True},
]

for rec in chart_of_accounts:
    rec["_ingested_at"] = str(datetime.now())

coa_df = spark.createDataFrame(chart_of_accounts)
coa_df.write.format("delta").mode("overwrite").option("mergeSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.bronze_chart_of_accounts")
print(f"Chart of Accounts: {coa_df.count()} rows")

# COMMAND ----------

cost_centers = [
    {"cost_center_code": "CC001", "cost_center_name": "Engineering", "department": "Technology", "budget_annual": 50000000.0},
    {"cost_center_code": "CC002", "cost_center_name": "Sales", "department": "Revenue", "budget_annual": 30000000.0},
    {"cost_center_code": "CC003", "cost_center_name": "Marketing", "department": "Revenue", "budget_annual": 15000000.0},
    {"cost_center_code": "CC004", "cost_center_name": "Finance", "department": "G&A", "budget_annual": 10000000.0},
    {"cost_center_code": "CC005", "cost_center_name": "HR", "department": "G&A", "budget_annual": 8000000.0},
    {"cost_center_code": "CC006", "cost_center_name": "Operations", "department": "Operations", "budget_annual": 25000000.0},
    {"cost_center_code": "CC007", "cost_center_name": "Legal", "department": "G&A", "budget_annual": 5000000.0},
    {"cost_center_code": "CC008", "cost_center_name": "Customer Success", "department": "Revenue", "budget_annual": 12000000.0},
]
for rec in cost_centers:
    rec["_ingested_at"] = str(datetime.now())

cc_df = spark.createDataFrame(cost_centers)
cc_df.write.format("delta").mode("overwrite").option("mergeSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.bronze_cost_centers")
print(f"Cost Centers: {cc_df.count()} rows")

# COMMAND ----------

# MAGIC %md ### P2P: Purchase Orders

# COMMAND ----------

vendor_ids = [f"VND{i:04d}" for i in range(1, VENDOR_COUNT + 1)]
cost_center_codes = [cc["cost_center_code"] for cc in cost_centers]
account_codes_expense = ["5000", "5100", "5200", "5300", "5400", "5500", "5600", "5800"]

po_statuses = ["APPROVED", "PARTIALLY_RECEIVED", "FULLY_RECEIVED", "CANCELLED", "PENDING_APPROVAL"]
po_types = ["STANDARD", "BLANKET", "SERVICE", "EMERGENCY"]

po_headers = []
po_lines = []

for i in range(1, PO_COUNT + 1):
    po_date = random_date(400, 10)
    vendor_id = random.choice(vendor_ids)
    num_lines = random.randint(1, 8)
    total_amount = 0.0

    po_id = f"PO{i:05d}"
    status = random.choices(po_statuses, weights=[40, 20, 25, 5, 10])[0]

    lines = []
    for j in range(1, num_lines + 1):
        unit_price = round(random.uniform(500, 150000), 2)
        qty = random.randint(1, 50)
        line_amount = round(unit_price * qty, 2)
        gst_rate = random.choice([0, 5, 12, 18, 28])
        gst_amount = round(line_amount * gst_rate / 100, 2)
        total_line = round(line_amount + gst_amount, 2)
        total_amount += total_line

        lines.append({
            "po_id": po_id,
            "line_number": j,
            "item_description": fake.catch_phrase(),
            "item_code": f"ITEM{random.randint(1000, 9999)}",
            "quantity": float(qty),
            "unit_of_measure": random.choice(["EA", "KG", "LTR", "MTR", "BOX", "HRS"]),
            "unit_price": unit_price,
            "line_amount": line_amount,
            "gst_rate": float(gst_rate),
            "gst_amount": gst_amount,
            "total_line_amount": total_line,
            "account_code": random.choice(account_codes_expense),
            "cost_center": random.choice(cost_center_codes),
            "_ingested_at": str(datetime.now()),
            "_source_system": "ERP_SAP"
        })
        po_lines.append(lines[-1])

    delivery_date = po_date + timedelta(days=random.randint(7, 60))
    po_headers.append({
        "po_id": po_id,
        "po_number": f"PO-{po_date.year}-{i:05d}",
        "vendor_id": vendor_id,
        "po_date": str(po_date),
        "delivery_date": str(delivery_date),
        "po_type": random.choice(po_types),
        "status": status,
        "total_amount": round(total_amount, 2),
        "currency": "INR",
        "requestor": fake.name(),
        "approver": fake.name(),
        "approved_date": str(po_date + timedelta(days=random.randint(1, 3))) if status != "PENDING_APPROVAL" else "",
        "company_code": random.choice(["CC_INDIA", "CC_USA", "CC_UK"]),
        "_ingested_at": str(datetime.now()),
        "_source_system": "ERP_SAP"
    })

po_header_df = spark.createDataFrame(po_headers)
po_header_df.write.format("delta").mode("overwrite").option("mergeSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.bronze_po_header")

po_line_df = spark.createDataFrame(po_lines)
po_line_df.write.format("delta").mode("overwrite").option("mergeSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.bronze_po_line")

print(f"PO Headers: {po_header_df.count()} rows")
print(f"PO Lines: {po_line_df.count()} rows")

# COMMAND ----------

# MAGIC %md ### P2P: Goods Receipt Notes (GRN)

# COMMAND ----------

approved_pos = [p["po_id"] for p in po_headers if p["status"] in ["PARTIALLY_RECEIVED", "FULLY_RECEIVED"]]

grns = []
for i, po_id in enumerate(approved_pos[:GRN_COUNT], 1):
    po = next(p for p in po_headers if p["po_id"] == po_id)
    po_date = datetime.strptime(po["po_date"], "%Y-%m-%d").date()
    grn_date = po_date + timedelta(days=random.randint(3, 30))

    receipt_qty_pct = random.uniform(0.5, 1.0) if po["status"] == "PARTIALLY_RECEIVED" else 1.0

    grns.append({
        "grn_id": f"GRN{i:05d}",
        "grn_number": f"GRN-{grn_date.year}-{i:05d}",
        "po_id": po_id,
        "vendor_id": po["vendor_id"],
        "grn_date": str(grn_date),
        "received_by": fake.name(),
        "warehouse_location": random.choice(["WH-MUMBAI-01", "WH-DELHI-01", "WH-BANGALORE-01", "WH-CHENNAI-01"]),
        "status": random.choice(["ACCEPTED", "PARTIALLY_ACCEPTED", "REJECTED"]),
        "received_qty_percentage": round(receipt_qty_pct * 100, 1),
        "received_amount": round(po["total_amount"] * receipt_qty_pct, 2),
        "quality_check_status": random.choices(["PASSED", "FAILED", "PENDING"], weights=[85, 5, 10])[0],
        "remarks": random.choice(["", "", "", "Partial delivery", "Item damaged", "Wrong quantity"]),
        "_ingested_at": str(datetime.now()),
        "_source_system": "ERP_SAP"
    })

grn_df = spark.createDataFrame(grns)
grn_df.write.format("delta").mode("overwrite").option("mergeSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.bronze_grn")
print(f"GRNs: {grn_df.count()} rows")

# COMMAND ----------

# MAGIC %md ### P2P: Invoices (with duplicates and mismatches for testing)

# COMMAND ----------

invoice_statuses = ["PENDING", "APPROVED", "PAID", "REJECTED", "UNDER_REVIEW", "DUPLICATE"]
matched_po_ids = [p["po_id"] for p in po_headers if p["status"] not in ["PENDING_APPROVAL", "CANCELLED"]]

p2p_invoices = []

# Regular invoices (matched to POs)
for i in range(1, INVOICE_COUNT + 1):
    use_po = random.random() < 0.85  # 85% have a PO reference
    po_id = random.choice(matched_po_ids) if use_po else None

    if po_id:
        po = next(p for p in po_headers if p["po_id"] == po_id)
        vendor_id = po["vendor_id"]
        po_amount = po["total_amount"]
        # Introduce amount mismatches in 10% of cases
        amount_factor = random.choices([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.05, 0.95, 1.10], k=1)[0]
        invoice_amount = round(po_amount * amount_factor, 2)
        invoice_date_base = datetime.strptime(po["po_date"], "%Y-%m-%d").date()
    else:
        vendor_id = random.choice(vendor_ids)
        invoice_amount = round(random.uniform(10000, 5000000), 2)
        invoice_date_base = random_date(300, 5)

    invoice_date = invoice_date_base + timedelta(days=random.randint(5, 45))
    tax_amount = round(invoice_amount * 0.18, 2)
    total_with_tax = round(invoice_amount + tax_amount, 2)

    due_days = 30 if not po_id else int(next((p for p in po_headers if p["po_id"] == po_id), {}).get("payment_terms", "NET30").replace("NET", "0"))
    due_date = invoice_date + timedelta(days=due_days)

    status = random.choices(invoice_statuses[:-1], weights=[25, 35, 25, 5, 10])[0]

    p2p_invoices.append({
        "invoice_id": f"INV{i:06d}",
        "invoice_number": f"VINV-{invoice_date.year}-{random.randint(10000,99999)}",
        "vendor_id": vendor_id,
        "po_id": po_id if po_id else "",
        "invoice_date": str(invoice_date),
        "due_date": str(due_date),
        "invoice_amount": invoice_amount,
        "tax_amount": tax_amount,
        "tax_rate": 18.0,
        "total_amount": total_with_tax,
        "currency": "INR",
        "payment_terms": random.choice(payment_terms_options),
        "status": status,
        "description": fake.bs(),
        "bank_account": fake.bban(),
        "gstin_vendor": random_gstin(),
        "hsn_sac_code": f"{random.randint(1000, 9999)}",
        "tds_applicable": random.choice([True, False]),
        "tds_rate": random.choice([0.0, 1.0, 2.0, 10.0]) if random.random() < 0.3 else 0.0,
        "_ingested_at": str(datetime.now()),
        "_source_system": "ERP_SAP"
    })

# Add duplicate invoices (5% duplicates)
duplicate_sources = random.sample(p2p_invoices, int(INVOICE_COUNT * 0.05))
for dup in duplicate_sources:
    dup_copy = dup.copy()
    dup_copy["invoice_id"] = f"INV{random.randint(900000, 999999)}"
    dup_copy["status"] = "DUPLICATE"
    dup_copy["_ingested_at"] = str(datetime.now())
    p2p_invoices.append(dup_copy)

p2p_invoice_df = spark.createDataFrame(p2p_invoices)
p2p_invoice_df.write.format("delta").mode("overwrite").option("mergeSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.bronze_p2p_invoices")
print(f"P2P Invoices: {p2p_invoice_df.count()} rows (includes duplicates)")

# COMMAND ----------

# MAGIC %md ### P2P: Payments

# COMMAND ----------

paid_invoices = [inv for inv in p2p_invoices if inv["status"] == "PAID"]
payment_methods = ["NEFT", "RTGS", "IMPS", "CHEQUE", "DD", "WIRE"]

p2p_payments = []
for i, inv in enumerate(paid_invoices, 1):
    inv_date = datetime.strptime(inv["invoice_date"], "%Y-%m-%d").date()
    payment_date = inv_date + timedelta(days=random.randint(15, 60))

    p2p_payments.append({
        "payment_id": f"PAY{i:06d}",
        "invoice_id": inv["invoice_id"],
        "vendor_id": inv["vendor_id"],
        "payment_date": str(payment_date),
        "payment_amount": inv["total_amount"],
        "currency": "INR",
        "payment_method": random.choice(payment_methods),
        "reference_number": f"REF{random.randint(10000000, 99999999)}",
        "bank_account": inv["bank_account"],
        "status": random.choices(["COMPLETED", "FAILED", "PENDING"], weights=[93, 3, 4])[0],
        "_ingested_at": str(datetime.now()),
        "_source_system": "ERP_SAP"
    })

p2p_payment_df = spark.createDataFrame(p2p_payments)
p2p_payment_df.write.format("delta").mode("overwrite").option("mergeSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.bronze_p2p_payments")
print(f"P2P Payments: {p2p_payment_df.count()} rows")

# COMMAND ----------

# MAGIC %md ### O2C: Sales Orders

# COMMAND ----------

customer_ids = [f"CUS{i:04d}" for i in range(1, CUSTOMER_COUNT + 1)]
so_statuses = ["CONFIRMED", "SHIPPED", "DELIVERED", "INVOICED", "CANCELLED"]
product_catalog = [
    {"product_code": "PROD001", "product_name": "Data Platform License", "category": "Software", "list_price": 500000.0},
    {"product_code": "PROD002", "product_name": "Analytics Suite", "category": "Software", "list_price": 250000.0},
    {"product_code": "PROD003", "product_name": "Implementation Services", "category": "Services", "list_price": 150000.0},
    {"product_code": "PROD004", "product_name": "Training Package", "category": "Services", "list_price": 80000.0},
    {"product_code": "PROD005", "product_name": "Support Contract Annual", "category": "Support", "list_price": 120000.0},
    {"product_code": "PROD006", "product_name": "Cloud Storage TB", "category": "Infrastructure", "list_price": 5000.0},
    {"product_code": "PROD007", "product_name": "API Gateway License", "category": "Software", "list_price": 180000.0},
    {"product_code": "PROD008", "product_name": "Security Module", "category": "Software", "list_price": 95000.0},
]

sales_orders = []
so_lines_all = []

for i in range(1, SO_COUNT + 1):
    so_date = random_date(500, 5)
    customer_id = random.choice(customer_ids)
    status = random.choices(so_statuses, weights=[15, 10, 20, 45, 10])[0]
    num_products = random.randint(1, 5)
    products = random.sample(product_catalog, min(num_products, len(product_catalog)))

    so_id = f"SO{i:05d}"
    total_amount = 0.0

    for j, prod in enumerate(products, 1):
        qty = random.randint(1, 20)
        discount_pct = random.choice([0, 5, 10, 15, 20])
        unit_price = prod["list_price"] * (1 - discount_pct / 100)
        line_amount = round(unit_price * qty, 2)
        gst_rate = 18.0
        gst_amount = round(line_amount * gst_rate / 100, 2)
        total_line = round(line_amount + gst_amount, 2)
        total_amount += total_line

        so_lines_all.append({
            "so_id": so_id,
            "line_number": j,
            "product_code": prod["product_code"],
            "product_name": prod["product_name"],
            "category": prod["category"],
            "quantity": float(qty),
            "list_price": prod["list_price"],
            "discount_percentage": float(discount_pct),
            "unit_price": round(unit_price, 2),
            "line_amount": line_amount,
            "gst_rate": gst_rate,
            "gst_amount": gst_amount,
            "total_line_amount": total_line,
            "_ingested_at": str(datetime.now()),
            "_source_system": "CRM_SALESFORCE"
        })

    expected_delivery = so_date + timedelta(days=random.randint(7, 45))
    sales_orders.append({
        "so_id": so_id,
        "so_number": f"SO-{so_date.year}-{i:05d}",
        "customer_id": customer_id,
        "so_date": str(so_date),
        "expected_delivery_date": str(expected_delivery),
        "actual_delivery_date": str(expected_delivery + timedelta(days=random.randint(-5, 15))) if status in ["DELIVERED", "INVOICED"] else "",
        "status": status,
        "total_amount": round(total_amount, 2),
        "currency": "INR",
        "sales_rep": fake.name(),
        "region": random.choice(["North", "South", "East", "West", "Central"]),
        "discount_approved_by": fake.name() if any(l.get("discount_percentage", 0) > 10 for l in so_lines_all[-num_products:]) else "",
        "_ingested_at": str(datetime.now()),
        "_source_system": "CRM_SALESFORCE"
    })

so_df = spark.createDataFrame(sales_orders)
so_df.write.format("delta").mode("overwrite").option("mergeSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.bronze_sales_orders")

so_line_df = spark.createDataFrame(so_lines_all)
so_line_df.write.format("delta").mode("overwrite").option("mergeSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.bronze_so_lines")

print(f"Sales Orders: {so_df.count()} rows")
print(f"SO Lines: {so_line_df.count()} rows")

# COMMAND ----------

# MAGIC %md ### O2C: Customer Invoices & Payments

# COMMAND ----------

invoiced_sos = [s for s in sales_orders if s["status"] == "INVOICED"]

o2c_invoices = []
for i, so in enumerate(invoiced_sos, 1):
    so_date = datetime.strptime(so["so_date"], "%Y-%m-%d").date()
    inv_date = so_date + timedelta(days=random.randint(1, 10))
    due_date = inv_date + timedelta(days=random.randint(30, 60))

    amount = so["total_amount"]
    tax = round(amount * 0.18 / 1.18, 2)

    o2c_invoices.append({
        "o2c_invoice_id": f"CINV{i:06d}",
        "invoice_number": f"SINV-{inv_date.year}-{random.randint(10000,99999)}",
        "so_id": so["so_id"],
        "customer_id": so["customer_id"],
        "invoice_date": str(inv_date),
        "due_date": str(due_date),
        "invoice_amount": round(amount - tax, 2),
        "tax_amount": tax,
        "total_amount": amount,
        "currency": "INR",
        "payment_terms": random.choice(payment_terms_options),
        "status": random.choices(["OUTSTANDING", "PAID", "OVERDUE", "PARTIAL_PAID", "WRITTEN_OFF"],
                                  weights=[25, 45, 15, 10, 5])[0],
        "_ingested_at": str(datetime.now()),
        "_source_system": "ERP_SAP"
    })

o2c_inv_df = spark.createDataFrame(o2c_invoices)
o2c_inv_df.write.format("delta").mode("overwrite").option("mergeSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.bronze_o2c_invoices")

# Customer payments
o2c_payments = []
paid_o2c = [inv for inv in o2c_invoices if inv["status"] in ["PAID", "PARTIAL_PAID"]]
for i, inv in enumerate(paid_o2c, 1):
    inv_date = datetime.strptime(inv["invoice_date"], "%Y-%m-%d").date()
    payment_date = inv_date + timedelta(days=random.randint(10, 50))
    pct_paid = 1.0 if inv["status"] == "PAID" else random.uniform(0.3, 0.9)

    o2c_payments.append({
        "receipt_id": f"RCP{i:06d}",
        "o2c_invoice_id": inv["o2c_invoice_id"],
        "customer_id": inv["customer_id"],
        "payment_date": str(payment_date),
        "payment_amount": round(inv["total_amount"] * pct_paid, 2),
        "currency": "INR",
        "payment_method": random.choice(["NEFT", "RTGS", "CHEQUE", "ONLINE"]),
        "reference_number": f"REF{random.randint(10000000,99999999)}",
        "status": "CLEARED",
        "_ingested_at": str(datetime.now()),
        "_source_system": "ERP_SAP"
    })

o2c_pay_df = spark.createDataFrame(o2c_payments)
o2c_pay_df.write.format("delta").mode("overwrite").option("mergeSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.bronze_o2c_payments")

print(f"O2C Invoices: {o2c_inv_df.count()} rows")
print(f"O2C Payments: {o2c_pay_df.count()} rows")

# COMMAND ----------

# MAGIC %md ### R2R: Journal Entries & General Ledger

# COMMAND ----------

je_types = ["MANUAL", "ACCRUAL", "REVERSAL", "SYSTEM_AUTO", "PAYROLL", "DEPRECIATION"]
account_codes_all = [a["account_code"] for a in chart_of_accounts]

journal_entries = []
je_lines = []

for i in range(1, 2001):  # 2000 journal entries
    je_date = random_date(365, 0)
    je_type = random.choice(je_types)
    cost_center = random.choice(cost_center_codes)

    je_id = f"JE{i:06d}"
    amount = round(random.uniform(1000, 10000000), 2)

    # Each JE has debit and credit (balanced)
    debit_account = random.choice(account_codes_all)
    credit_account = random.choice([a for a in account_codes_all if a != debit_account])

    journal_entries.append({
        "je_id": je_id,
        "je_number": f"JE-{je_date.year}-{i:06d}",
        "je_date": str(je_date),
        "je_type": je_type,
        "description": fake.bs(),
        "period": f"{je_date.year}-{je_date.month:02d}",
        "fiscal_year": je_date.year,
        "posted_by": fake.name(),
        "approved_by": fake.name() if je_type != "SYSTEM_AUTO" else "SYSTEM",
        "status": random.choices(["POSTED", "DRAFT", "REVERSED"], weights=[85, 10, 5])[0],
        "total_debit": amount,
        "total_credit": amount,
        "_ingested_at": str(datetime.now()),
        "_source_system": "ERP_SAP"
    })

    # Debit line
    je_lines.append({
        "je_id": je_id,
        "line_number": 1,
        "account_code": debit_account,
        "cost_center": cost_center,
        "debit_amount": amount,
        "credit_amount": 0.0,
        "description": fake.catch_phrase(),
        "_ingested_at": str(datetime.now())
    })
    # Credit line
    je_lines.append({
        "je_id": je_id,
        "line_number": 2,
        "account_code": credit_account,
        "cost_center": cost_center,
        "debit_amount": 0.0,
        "credit_amount": amount,
        "description": fake.catch_phrase(),
        "_ingested_at": str(datetime.now())
    })

je_df = spark.createDataFrame(journal_entries)
je_df.write.format("delta").mode("overwrite").option("mergeSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.bronze_journal_entries")

je_lines_df = spark.createDataFrame(je_lines)
je_lines_df.write.format("delta").mode("overwrite").option("mergeSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.bronze_je_lines")

print(f"Journal Entries: {je_df.count()} rows")
print(f"JE Lines: {je_lines_df.count()} rows")

# COMMAND ----------

# MAGIC %md ### Raw Invoice Documents (for AI Processing)

# COMMAND ----------

def generate_raw_invoice_text(inv):
    vendor = random.choice(vendors)
    lines = []
    num_items = random.randint(1, 5)
    subtotal = 0

    items_text = ""
    for k in range(1, num_items + 1):
        desc = fake.catch_phrase()
        qty = random.randint(1, 20)
        rate = round(random.uniform(1000, 50000), 2)
        amount = round(qty * rate, 2)
        subtotal += amount
        items_text += f"\n  {k}. {desc:<45} Qty: {qty:>3}  Rate: {rate:>10,.2f}  Amount: {amount:>12,.2f}"

    gst_rate = random.choice([5, 12, 18, 28])
    cgst = round(subtotal * gst_rate / 200, 2)
    sgst = round(subtotal * gst_rate / 200, 2)
    total = round(subtotal + cgst + sgst, 2)

    inv_date = datetime.strptime(inv["invoice_date"], "%Y-%m-%d").date()
    due_date = inv_date + timedelta(days=30)

    text = f"""
================================================================================
                            TAX INVOICE
================================================================================
Vendor: {vendor['vendor_name'].upper()}
Address: {vendor['address_line1']}, {vendor['city']}, {vendor['state']}
GSTIN: {vendor['gstin'] or 'N/A'}
Phone: {vendor['contact_phone']}
Email: {vendor['contact_email']}
--------------------------------------------------------------------------------
Invoice No: {inv['invoice_number']}
Invoice Date: {inv_date.strftime('%d-%b-%Y')}
Due Date: {due_date.strftime('%d-%b-%Y')}
PO Reference: {inv.get('po_id', 'N/A')}
--------------------------------------------------------------------------------
ITEMS:
{items_text}
--------------------------------------------------------------------------------
                                          Subtotal:  INR {subtotal:>14,.2f}
                                          CGST @{gst_rate//2}%: INR {cgst:>14,.2f}
                                          SGST @{gst_rate//2}%: INR {sgst:>14,.2f}
                                          TOTAL:     INR {total:>14,.2f}
--------------------------------------------------------------------------------
Payment Details:
  Bank: State Bank of India
  Account No: {vendor['bank_account']}
  IFSC: {vendor['bank_ifsc'] or 'SBIN0001234'}
--------------------------------------------------------------------------------
Declaration: I/We hereby certify that the goods/services mentioned above
have been supplied and the payment mentioned is legally due.
================================================================================
"""
    return text

# Generate raw invoice files and store structured JSON in bronze
raw_invoice_records = []
sample_invoices = random.sample(p2p_invoices, min(200, len(p2p_invoices)))

for inv in sample_invoices:
    raw_text = generate_raw_invoice_text(inv)

    # Save raw text file to volume
    file_path = f"{VOLUME_PATH}/{inv['invoice_id']}.txt"
    with open(file_path, 'w') as f:
        f.write(raw_text)

    raw_invoice_records.append({
        "invoice_id": inv["invoice_id"],
        "raw_text": raw_text,
        "file_path": file_path,
        "file_type": "TXT",
        "vendor_id": inv["vendor_id"],
        "processing_status": "PENDING",
        "_ingested_at": str(datetime.now()),
        "_source_system": "FILE_SCAN"
    })

raw_inv_df = spark.createDataFrame(raw_invoice_records)
raw_inv_df.write.format("delta").mode("overwrite").option("mergeSchema", "true").saveAsTable(f"{CATALOG}.{SCHEMA}.bronze_raw_invoice_documents")
print(f"Raw Invoice Documents: {raw_inv_df.count()} rows")
print(f"Files saved to: {VOLUME_PATH}")

# COMMAND ----------

# MAGIC %md ## Summary

# COMMAND ----------

tables = [
    "bronze_vendors", "bronze_customers", "bronze_chart_of_accounts", "bronze_cost_centers",
    "bronze_po_header", "bronze_po_line", "bronze_grn",
    "bronze_p2p_invoices", "bronze_p2p_payments",
    "bronze_sales_orders", "bronze_so_lines",
    "bronze_o2c_invoices", "bronze_o2c_payments",
    "bronze_journal_entries", "bronze_je_lines",
    "bronze_raw_invoice_documents"
]

print("=" * 60)
print("DATA GENERATION COMPLETE")
print("=" * 60)
for tbl in tables:
    count = spark.table(f"{CATALOG}.{SCHEMA}.{tbl}").count()
    print(f"  {tbl:<45} {count:>6} rows")
print("=" * 60)
