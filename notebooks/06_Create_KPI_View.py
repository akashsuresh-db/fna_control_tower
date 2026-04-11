# Databricks notebook source
# MAGIC %md
# MAGIC # Create Unified Finance KPI View
# MAGIC
# MAGIC Creates `gold_finance_kpis` view from Gold P2P/O2C/R2R tables.
# MAGIC Parameterized to work with any catalog/schema via DAB job parameters.

# COMMAND ----------

dbutils.widgets.text("catalog", "hp_sf_test", "Unity Catalog")
dbutils.widgets.text("schema", "finance_and_accounting", "Schema")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")

FQN = f"{CATALOG}.{SCHEMA}"

print(f"Creating KPI view in: {FQN}")

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE VIEW {FQN}.gold_finance_kpis
COMMENT 'Unified finance KPI snapshot covering P2P, O2C, and R2R metrics. One row per snapshot date. Use this view to answer questions about DSO, DPO, touchless rate, AP/AR balances, aging, and working capital.'
AS

WITH

p2p AS (
  SELECT
    COUNT(*)                                                                      AS total_invoices,
    COUNT(CASE WHEN invoice_status = 'PENDING'  THEN 1 END)                      AS invoices_pending,
    COUNT(CASE WHEN invoice_status = 'APPROVED' THEN 1 END)                      AS invoices_approved,
    COUNT(CASE WHEN invoice_status = 'PAID'     THEN 1 END)                      AS invoices_paid,
    COUNT(CASE WHEN is_overdue = true           THEN 1 END)                      AS ap_invoices_overdue,
    COUNT(CASE WHEN match_status = 'THREE_WAY_MATCHED'  THEN 1 END)              AS three_way_matched_count,
    COUNT(CASE WHEN match_status = 'TWO_WAY_MATCHED'    THEN 1 END)              AS two_way_matched_count,
    COUNT(CASE WHEN match_status = 'AMOUNT_MISMATCH'    THEN 1 END)              AS amount_mismatch_count,
    COUNT(CASE WHEN match_status = 'NO_PO_REFERENCE'    THEN 1 END)              AS no_po_reference_count,
    SUM(CASE WHEN invoice_status != 'PAID' THEN invoice_total_inr ELSE 0 END)    AS ap_outstanding_inr,
    SUM(CASE WHEN is_overdue = true        THEN invoice_total_inr ELSE 0 END)    AS ap_overdue_inr,
    SUM(CASE WHEN aging_bucket = '0-30 days'  AND invoice_status != 'PAID'
             THEN invoice_total_inr ELSE 0 END)                                  AS ap_aging_0_30_inr,
    SUM(CASE WHEN aging_bucket = '31-60 days' AND invoice_status != 'PAID'
             THEN invoice_total_inr ELSE 0 END)                                  AS ap_aging_31_60_inr,
    SUM(CASE WHEN aging_bucket = '61-90 days' AND invoice_status != 'PAID'
             THEN invoice_total_inr ELSE 0 END)                                  AS ap_aging_61_90_inr,
    SUM(CASE WHEN aging_bucket = '90+ days'   AND invoice_status != 'PAID'
             THEN invoice_total_inr ELSE 0 END)                                  AS ap_aging_90_plus_inr,
    SUM(invoice_total_inr)                                                       AS total_ap_spend_inr,
    AVG(invoice_total_inr)                                                       AS avg_invoice_amount_inr,
    AVG(CASE WHEN invoice_status = 'PAID' THEN days_to_pay END)                 AS avg_days_to_pay
  FROM {FQN}.gold_fact_invoices
),

dpo AS (
  SELECT
    CASE
      WHEN SUM(invoice_total_inr) > 0
      THEN ROUND(
             SUM(CASE WHEN invoice_status != 'PAID' THEN invoice_total_inr ELSE 0 END)
             / SUM(invoice_total_inr) * 90, 1)
    END AS dpo_days
  FROM {FQN}.gold_fact_invoices
),

o2c AS (
  SELECT
    SUM(balance_outstanding)                                                        AS ar_outstanding_inr,
    SUM(CASE WHEN days_overdue > 0 THEN balance_outstanding ELSE 0 END)             AS ar_overdue_inr,
    SUM(CASE WHEN aging_bucket = '0-30 days'  THEN balance_outstanding ELSE 0 END)  AS ar_aging_0_30_inr,
    SUM(CASE WHEN aging_bucket = '31-60 days' THEN balance_outstanding ELSE 0 END)  AS ar_aging_31_60_inr,
    SUM(CASE WHEN aging_bucket = '61-90 days' THEN balance_outstanding ELSE 0 END)  AS ar_aging_61_90_inr,
    SUM(CASE WHEN aging_bucket = '90+ days'   THEN balance_outstanding ELSE 0 END)  AS ar_aging_90_plus_inr,
    COUNT(*)                                                                         AS total_ar_invoices,
    COUNT(CASE WHEN days_overdue > 0        THEN 1 END)                             AS ar_invoices_overdue,
    COUNT(CASE WHEN is_fully_collected      THEN 1 END)                             AS ar_invoices_collected,
    SUM(amount_collected_inr)                                                        AS total_collected_inr,
    SUM(invoice_total_inr)                                                           AS total_billed_inr,
    AVG(CASE WHEN is_fully_collected THEN days_to_collect END)                       AS avg_days_to_collect,
    AVG(CASE WHEN days_overdue > 0   THEN days_overdue    END)                       AS avg_days_overdue
  FROM {FQN}.gold_fact_collections
),

dso AS (
  SELECT
    CASE
      WHEN SUM(invoice_total_inr) > 0
      THEN ROUND(SUM(balance_outstanding) / SUM(invoice_total_inr) * 90, 1)
    END AS dso_days,
    CASE
      WHEN SUM(invoice_total_inr) > 0
      THEN ROUND(SUM(amount_collected_inr) / SUM(invoice_total_inr) * 100, 1)
    END AS collection_rate_pct
  FROM {FQN}.gold_fact_collections
),

revenue AS (
  SELECT
    COUNT(*)                                                     AS total_sales_orders,
    SUM(so_total_inr)                                            AS total_revenue_inr,
    AVG(so_total_inr)                                            AS avg_order_value_inr,
    COUNT(CASE WHEN status = 'COMPLETED' THEN 1 END)             AS completed_orders,
    SUM(CASE WHEN status = 'COMPLETED' THEN so_total_inr END)    AS completed_revenue_inr
  FROM {FQN}.gold_fact_sales
),

overdue_customers AS (
  SELECT
    COUNT(CASE WHEN overdue_invoices > 0          THEN 1 END)   AS customers_with_overdue,
    COUNT(CASE WHEN credit_utilization_pct > 90   THEN 1 END)   AS customers_near_credit_limit,
    COUNT(CASE WHEN dso > 60                      THEN 1 END)   AS customers_high_dso,
    COUNT(*)                                                     AS total_active_customers
  FROM {FQN}.gold_dim_customer
  WHERE is_active = true
),

gl AS (
  SELECT
    COUNT(DISTINCT je_id)                                        AS total_journal_entries,
    COUNT(*)                                                     AS total_gl_lines,
    SUM(debit_inr)                                               AS total_debits_inr,
    SUM(credit_inr)                                              AS total_credits_inr,
    ABS(SUM(debit_inr) - SUM(credit_inr))                       AS gl_imbalance_inr,
    MAX(je_date)                                                 AS last_je_date
  FROM {FQN}.gold_fact_gl
),

tb AS (
  SELECT
    SUM(CASE WHEN account_type = 'Asset'     THEN closing_balance_inr ELSE 0 END)  AS total_assets_inr,
    SUM(CASE WHEN account_type = 'Liability' THEN closing_balance_inr ELSE 0 END)  AS total_liabilities_inr,
    SUM(CASE WHEN account_type = 'Equity'    THEN closing_balance_inr ELSE 0 END)  AS total_equity_inr,
    SUM(CASE WHEN account_type = 'Revenue'   THEN closing_balance_inr ELSE 0 END)  AS total_revenue_gl_inr,
    SUM(CASE WHEN account_type = 'Expense'   THEN closing_balance_inr ELSE 0 END)  AS total_expenses_inr
  FROM {FQN}.gold_fact_trial_balance
  WHERE period = (
    SELECT MAX(period) FROM {FQN}.gold_fact_trial_balance
  )
)

SELECT
  CURRENT_DATE()                                                          AS snapshot_date,
  p2p.total_invoices,
  p2p.invoices_pending,
  p2p.invoices_approved,
  p2p.invoices_paid,
  p2p.ap_invoices_overdue,
  p2p.three_way_matched_count,
  p2p.two_way_matched_count,
  p2p.amount_mismatch_count,
  p2p.no_po_reference_count,
  ROUND(p2p.three_way_matched_count / NULLIF(p2p.total_invoices, 0) * 100, 1)  AS touchless_rate_pct,
  ROUND(p2p.amount_mismatch_count   / NULLIF(p2p.total_invoices, 0) * 100, 1)  AS amount_mismatch_rate_pct,
  ROUND(p2p.no_po_reference_count   / NULLIF(p2p.total_invoices, 0) * 100, 1)  AS no_po_rate_pct,
  ROUND(p2p.ap_outstanding_inr,    2)   AS ap_outstanding_inr,
  ROUND(p2p.ap_overdue_inr,        2)   AS ap_overdue_inr,
  ROUND(p2p.total_ap_spend_inr,    2)   AS total_ap_spend_inr,
  ROUND(p2p.avg_invoice_amount_inr,2)   AS avg_invoice_amount_inr,
  ROUND(p2p.ap_aging_0_30_inr,     2)   AS ap_aging_0_30_inr,
  ROUND(p2p.ap_aging_31_60_inr,    2)   AS ap_aging_31_60_inr,
  ROUND(p2p.ap_aging_61_90_inr,    2)   AS ap_aging_61_90_inr,
  ROUND(p2p.ap_aging_90_plus_inr,  2)   AS ap_aging_90_plus_inr,
  dpo.dpo_days,
  ROUND(p2p.avg_days_to_pay,       1)   AS avg_days_to_pay,
  o2c.total_ar_invoices,
  o2c.ar_invoices_overdue,
  o2c.ar_invoices_collected,
  ROUND(o2c.ar_outstanding_inr,    2)   AS ar_outstanding_inr,
  ROUND(o2c.ar_overdue_inr,        2)   AS ar_overdue_inr,
  ROUND(o2c.total_collected_inr,   2)   AS total_collected_inr,
  ROUND(o2c.total_billed_inr,      2)   AS total_billed_inr,
  ROUND(o2c.ar_aging_0_30_inr,     2)   AS ar_aging_0_30_inr,
  ROUND(o2c.ar_aging_31_60_inr,    2)   AS ar_aging_31_60_inr,
  ROUND(o2c.ar_aging_61_90_inr,    2)   AS ar_aging_61_90_inr,
  ROUND(o2c.ar_aging_90_plus_inr,  2)   AS ar_aging_90_plus_inr,
  dso.dso_days,
  dso.collection_rate_pct,
  ROUND(o2c.avg_days_to_collect,   1)   AS avg_days_to_collect,
  ROUND(o2c.avg_days_overdue,      1)   AS avg_days_overdue,
  oc.total_active_customers,
  oc.customers_with_overdue,
  oc.customers_near_credit_limit,
  oc.customers_high_dso,
  ROUND(oc.customers_with_overdue / NULLIF(oc.total_active_customers, 0) * 100, 1)
                                         AS pct_customers_overdue,
  revenue.total_sales_orders,
  ROUND(revenue.total_revenue_inr,     2)  AS total_revenue_inr,
  ROUND(revenue.avg_order_value_inr,   2)  AS avg_order_value_inr,
  ROUND(revenue.completed_revenue_inr, 2)  AS completed_revenue_inr,
  gl.total_journal_entries,
  gl.total_gl_lines,
  ROUND(gl.total_debits_inr,  2)         AS total_debits_inr,
  ROUND(gl.total_credits_inr, 2)         AS total_credits_inr,
  ROUND(gl.gl_imbalance_inr,  2)         AS gl_imbalance_inr,
  gl.last_je_date,
  ROUND(tb.total_assets_inr,       2)    AS total_assets_inr,
  ROUND(tb.total_liabilities_inr,  2)    AS total_liabilities_inr,
  ROUND(tb.total_equity_inr,       2)    AS total_equity_inr,
  ROUND(tb.total_revenue_gl_inr,   2)    AS total_revenue_gl_inr,
  ROUND(tb.total_expenses_inr,     2)    AS total_expenses_inr,
  ROUND(COALESCE(tb.total_revenue_gl_inr, 0) - COALESCE(tb.total_expenses_inr, 0), 2)
                                          AS net_income_inr,
  ROUND(COALESCE(o2c.ar_outstanding_inr, 0) - COALESCE(p2p.ap_outstanding_inr, 0), 2)
                                          AS working_capital_inr,
  ROUND(COALESCE(dso.dso_days, 0) - COALESCE(dpo.dpo_days, 0), 1)
                                          AS cash_conversion_cycle_days,
  ROUND(COALESCE(p2p.ap_outstanding_inr, 0) / NULLIF(o2c.ar_outstanding_inr, 0), 2)
                                          AS ap_ar_ratio
FROM p2p
CROSS JOIN dpo
CROSS JOIN o2c
CROSS JOIN dso
CROSS JOIN revenue
CROSS JOIN overdue_customers oc
CROSS JOIN gl
CROSS JOIN tb
""")

print(f"View {FQN}.gold_finance_kpis created successfully")
