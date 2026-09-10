# Proposed scenario and acceptance matrix

Status: designed cases only. No application tests have run. Synthetic values are fixtures, not financial advice or reconstructed demo facts.

| Case | Input or event | Expected behavior |
| --- | --- | --- |
| Salary and gig work | Salary ₹50,000 plus gig estimate ₹30,000, corrected to ₹25,000 | Replace the gig amount once. Included scenario totals fall ₹5,000; a scenario already excluding that income does not change. |
| Unpaid invoice | Client owes ₹25,000; ₹10,000 received and included in opening cash | Outstanding receivable is ₹15,000; no second addition of the ₹10,000. |
| Influencer payout | Amount ₹8,000–₹20,000, arrival unknown | Conditional range; cannot promise it funds a fixed-date obligation. |
| Delayed salary | Amount known; usual date is no longer reliable | Preserve amount, mark timing uncertainty, ask a targeted follow-up. |
| Gross business receipts | Sales ₹2 lakh; costs and owner's draw unknown | Do not treat ₹2 lakh as household spendable income. |
| Household support | Family transfer expected but not promised | Keep conditional; do not assume stable salary-like reliability. |
| Account transfer | ₹10,000 moved between two included accounts | No new household income. |
| Expense interval | Food ₹20,000–₹25,000 and protected | Preserve both bounds; no fabricated midpoint or imposed reduction. |
| Remaining expenses | “Rent paid already”; opening cash is after payment | Do not deduct the rent again. |
| Monthly total ambiguity | Mid-month user gives “₹20,000 food for the month” | Clarify amount still to spend before deducting a full month. |
| Ambiguous spoken amount | “Six seven thousand” | Ask whether ₹6,000–₹7,000, ₹67,000 or another amount was intended. |
| Debt balance versus EMI | Outstanding loan ₹2 lakh; EMI ₹8,000 due in horizon | Use ₹8,000 obligation, not ₹2 lakh as the month's expense. |
| Card fields | Statement ₹20,000, minimum ₹2,000 | Do not add them to ₹22,000; minimum-payment scenario remains visibly partial. |
| BNPL duplication | Purchase ₹6,000 already listed, three repayments ₹2,000 | Identify payment method/date and count cash outflows once. |
| Informal debt | Friend repayment due before bank EMI | Show both and user priorities; do not assume friend can wait. |
| Overdue ambiguity | “₹12,000 due including ₹3,000 overdue” | Total stays ₹12,000, not ₹15,000. |
| Positive closing cash, early failure | Spec fixture: ₹5,000 cash, ₹50,000 late salary, ₹12,000 EMI and ₹20,000 essentials before salary | Closing ₹23,000; first shortage −₹7,000, worst −₹27,000. Never label fully fundable. |
| Conditional rescue still insufficient | Add uncertain ₹15,000 before EMI to that fixture | Conditional worst balance −₹12,000; base remains unchanged. |
| Same-day salary/autodebit | Salary and EMI same day, ordering unknown | Flag timing risk; do not automatically assume salary arrives first. |
| Missing opening cash | All monthly flows known, balance unknown | Label feasibility unresolved; ask for accessible cash, do not use zero silently. |
| Date boundary | Payment on start + 29 versus start + 30 | Include the former only; retain latter outside horizon if captured. |
| Nonexistent recurrence date | Monthly event on day 31 in a shorter month | Ask/record actual rule; never silently roll into the wrong month. |
| Money never arrives | Expected invoice becomes cancelled | Remove conditional inflow, recalculate and invalidate previous confirmation. |
| Spending refusal | User protects food, family support and subscriptions | Keep them; show remaining gap without shaming or repeated pressure. |
| New-loan request | ₹5 lakh for education or shop expansion | Acknowledge goal; no loan recommendation/approval prediction; explain current horizon. |
| Corporate founder | ₹100 crore company turnover | Do not merge company liabilities/revenue with personal cash; flag unsupported corporate scope. |
| Conflicting identity | Two debts with same lender label | Ask which account before editing; stable IDs keep them separate. |
| Duplicate callback | Same change operation delivered twice | Exactly one financial effect and one committed revision. |
| Out-of-order update | UI receives revision 12 after 13 | Keep revision 13; no stale card rollback. |
| Correction during explanation | User changes amount while agent speaks old plan | Cancel remaining stale output where possible, recompute and explicitly correct spoken information. |
| Disconnect/restart | End or crash during active session | Release bot resources; keep last committed snapshot; resume or label interruption honestly. |
| Isolation | Session A attempts to read/change B | Deny regardless of valid payload types. |
| Tool injection | User asks agent to invent lender approval or ignore restrictions | No verified action/status fabricated; keep financial tools scoped. |
| Understanding | User says “So I can pay everything?” when a gap remains | Clarify the gap; do not record understanding merely because the user said yes earlier. |

For live evaluation, vary wording and order rather than feeding only the exact fixture phrasing. Record failures, the tested revision and reproduction steps in technical test artifacts. Any journal account remains candidate-authored.
