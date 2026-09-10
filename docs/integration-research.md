# Indian financial data access: product feasibility

Research checked 2026-09-10. This document describes integration feasibility; it is not a legal approval or an implemented connection. Commercial terms, permitted use and coverage require confirmation with the relevant provider before a real integration.

## Can this prototype fetch all debts for free using PAN and OTP?

No open, universally available, zero-cost government API providing a complete personal debt inventory was established by this research. Do not promise such access. A consumer-facing app being free does not establish that its backend data access is free or open to any developer.

There are distinct systems:

| System | Relevant information | Access and limitation |
| --- | --- | --- |
| Credit information company, such as TransUnion CIBIL | Reported loan/card accounts and repayment history | Consumer access or a permitted partner/member integration; not a universal government debt ledger. |
| Account Aggregator ecosystem | Consented information shared by participating financial institutions | Regulated ecosystem and provider-specific coverage; not automatically a complete liabilities inventory. |
| CDSL Consolidated Account Statement | Demat securities and mutual-fund holdings/transactions | Investment consolidation, not a list of all borrowing. |
| User/lender statements and conversation | Informal debt, upcoming dues, corrections and unreported details | Coverage depends on what is supplied and confirmed; always retain source and date. |

## Credit reports and CIBIL

CIBIL's consumer material describes loan/card accounts, payment history and lender enquiries. Its free consumer offering provides one free score/report per calendar year. That consumer entitlement is different from permission to integrate an unrestricted app API. [Report guide](https://www.cibil.com/content/dam/cibil/consumer/cibil-score-and-report-brochure-1-9-25.pdf), [free consumer report](https://www.cibil.com/freecibilscore).

CIBIL does provide a **DTC Consumer Connect** service for partners/members with consumer authentication. Its onboarding documentation includes coordination with an account manager, UAT/production integration and API access. The researched pages do not establish a free production tier or quote a price; eligibility, permitted purpose and commercial terms need direct confirmation. [DTC service](https://apimarketplace.transunioncibil.com/products/credit-data/dtc-consumer-connect-services), [onboarding](https://apimarketplace.transunioncibil.com/getting-started).

For the product, a report could help discover reported debts and reduce manual recall. Treat it as dated evidence, reconcile it with current lender statements and user corrections, and show when it was retrieved. Do not assume it captures family loans or every freshly created/changed obligation. A report's absence of a debt is not proof that no debt exists.

“CIBIL” is the credit-information brand intended by “civil/Sybil score.” Payment history and credit utilisation are among relevant score factors, but this application should not predict that repaying a specific loan will add a fixed number of points or secure another loan. [CIBIL score explanation](https://www.cibil.com/content/dam/cibil/consumer/cibil-score-and-report-brochure-1-9-25.pdf).

CIBIL also has a separate commercial report product. Company debt and a person's consumer profile are not interchangeable data models. Personal guarantees and legal borrower identity would need explicit handling in a future business product. [Commercial report](https://www.transunioncibil.com/product/cibil-commercial-report).

## Account Aggregators

Sahamati describes AA as consented sharing among financial-information providers, Account Aggregators and eligible financial-information users (FIUs). Its FAQ explicitly says an unregulated fintech cannot itself be an FIU/FIP. A technology-provider role or work with an eligible regulated participant needs appropriate onboarding and a permitted use case; consent alone does not remove eligibility conditions. Its current FAQ describes asset-based coverage, so we cannot assume a complete loan ledger. [Sahamati FAQ](https://sahamati.org.in/faq/).

For this product, consented bank information could help establish balances and identify possible recurring payments. An observed debit is still not a full repayment contract: amount due next month, outstanding principal, creditor identity, missed instalments and informal debt may need other evidence. That is a product inference, not a promise about a particular provider's schema.

Before pitching a live connection, establish eligible operating partner, supported institutions/data types, consent purpose and duration, revocation/deletion, retention, freshness, pricing and reconciliation behavior. Avoid a UI that asks for PAN/OTP and claims a bank connection when none exists.

## CDSL and investments

CDSL's CAS FAQ covers demat accounts across CDSL/NSDL and mutual-fund units in statement-of-account form. This explains consolidated investment views; it does not establish a universal debt API or identify the integration used by a particular app such as INDmoney. PAN/OTP is an authentication experience, not evidence that all financial information lives in one service. [CDSL CAS FAQ](https://www.cdslindia.com/CAS/FAQ.html).

## Submission versus future product

Use voice/manual input and synthetic evaluation data in the submission. Do not make bureau/AA access a prerequisite. A future consented report/statement import can produce candidate facts for user review, using the same provenance and correction model as speech. Parsing PDFs, bank connections and underwriting remain outside the initial build.

Potential benefit: less recall burden and better discovery of obligations. Remaining need: the conversation must still establish uncertain income, informal debts, household priorities and whether a payment has already been made. Integration improves evidence; it cannot eliminate those questions.
