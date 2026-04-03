# Tasks

## Status Legend
- [ ] TODO
- [x] DONE
- [~] IN PROGRESS

## Tasks

- [x] Create DEMO.md and TASKS.md
- [x] Write 00_Setup_and_Data_Generation notebook
- [x] Write 01_DLT_Pipeline notebook (Bronze + Silver with DLT expectations)
- [x] Write 02_Gold_Layer_P2P notebook
- [x] Write 03_Gold_Layer_O2C notebook
- [x] Write 04_Gold_Layer_R2R notebook
- [x] Write 05_Invoice_AI_Processing notebook
- [x] Write 06_Genie_Space_Setup notebook
- [x] Upload all notebooks to Databricks workspace
- [x] Create DLT pipeline (ID: 20b7318a-de2e-4d35-9a08-03fccc7a4ff9)
- [x] Run 00_Setup_and_Data_Generation (100 vendors, 150 customers, 500 POs, 577 invoices, 2000 JEs)
- [x] Run DLT pipeline (Bronze → Silver) - COMPLETED, all tables materialized
- [x] Run Gold layer notebooks (P2P, O2C, R2R) - All 8 gold tables created
- [x] Run Invoice AI Processing (50 invoices extracted with Claude Sonnet)
- [x] Fix Invoice AI Processing to use ai_parse_document (VARIANT :content::string syntax) + re-run successfully
- [x] Create Genie space (ID: 01f122c95c741815919b6457017f0899)
- [ ] Add gold tables to Genie space via UI (manual step - see instructions below)

## Genie Space - Manual Table Addition Required

**Space URL**: https://adb-984752964297111.11.azuredatabricks.net/genie/spaces/01f122c95c741815919b6457017f0899

1. Open the URL above in your browser
2. Click the gear/settings icon in the top right
3. Select "Edit Space"
4. Click "Add Table" and add each of these:
   - akash_s_demo.finance_and_accounting.gold_dim_vendor
   - akash_s_demo.finance_and_accounting.gold_fact_invoices
   - akash_s_demo.finance_and_accounting.gold_fact_payments
   - akash_s_demo.finance_and_accounting.gold_dim_customer
   - akash_s_demo.finance_and_accounting.gold_fact_sales
   - akash_s_demo.finance_and_accounting.gold_fact_collections
   - akash_s_demo.finance_and_accounting.gold_fact_gl
   - akash_s_demo.finance_and_accounting.gold_fact_trial_balance
