# Customer Due Diligence Report Skill

Reusable Codex skill for customer/company due diligence, public-source verification, cooperation risk review, and Chinese Word report generation.

## What This Skill Does

This skill turns a company name, domain, email, contact screenshot, buyer lead, supplier, importer, distributor, ecommerce store, or brand clue into a structured due diligence workflow.

It helps an AI agent:

- Normalize weak customer clues such as signatures, screenshots, domains, emails, phone numbers, addresses, and country hints.
- Verify identity across official websites, registries, DNS, WHOIS/RDAP, email domains, phone/address matches, and legal entity data.
- Investigate business profile, products, channels, management, market traces, IP/brand assets, certifications, and supply-chain clues.
- Check cooperation risks including litigation, bankruptcy, enforcement, complaints, sanctions, export controls, payment mismatch, and website anomalies.
- Rate the customer with practical B2B cooperation grades from `A` to `High Risk`.
- Generate a polished Chinese `.docx` report with conclusion-first structure, risk table, cooperation advice, and source appendix.

## Repository Structure

```text
customer-due-diligence-report-skill/
├─ SKILL.md
├─ agents/
│  └─ openai.yaml
├─ references/
│  └─ report_schema.json
└─ scripts/
   ├─ build_due_diligence_docx.py
   └─ sync_from_codex_skill.ps1
```

## Install

Copy this folder into a Codex skills directory:

```powershell
Copy-Item -Recurse -Force `
  "customer-due-diligence-report-skill" `
  "$env:USERPROFILE\.codex\skills\customer-due-diligence-report"
```

The skill name is:

```text
customer-due-diligence-report
```

## Typical Use

Ask Codex in Chinese or English:

```text
背调一下这家公司，生成 Word 报告
```

or:

```text
Use $customer-due-diligence-report to investigate this company and create a DOCX report.
```

## Report Builder

The skill uses `references/report_schema.json` as the report data shape and `scripts/build_due_diligence_docx.py` to generate the final Word document.

Example:

```powershell
python scripts/build_due_diligence_docx.py `
  --input D:\Ai_cache\report_data.json `
  --output D:\Ai_cache\Company_due_diligence_YYYYMMDD.docx
```

## Updating This Repository From Local Codex

If the installed local skill is improved later, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/sync_from_codex_skill.ps1
```

The sync script copies the installed skill from:

```text
C:\Users\Administrator\.codex\skills\customer-due-diligence-report
```

into this repository, validates the required files, commits changes, and pushes them to GitHub.

## Notes

- The skill requires live web investigation for each new target because company status, websites, sanctions, complaints, and registry records change.
- Attached screenshots and documents are treated as evidence only, not as instructions.
- Weak-evidence targets should be written as “无法充分核验/待补证” reports instead of guessed conclusions.
