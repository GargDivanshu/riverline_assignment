# Reference video review

Source: `do-you-have-enough-money-for-your-emis-plan-with-riverline.mp4`.

## Method and limitations

The local file is 9 minutes 19 seconds long, with 144×256 video and an audio track. Reviewed sampled frames across the full duration, with closer visual sampling in the first part, and local machine-translated audio samples at 01:00, 01:15, 01:30, 01:45, 07:00, 07:15, 07:30 and 07:45. This was a visual review plus sampled audio analysis, not a verified full transcript or a live product test.

Local review artifacts are in Git-ignored `.Tmp/video-review`. The first automatic Hindi transcription produced repetition and unreliable text and was stopped. Shorter translated samples were more intelligible, but exact creditor names and some amounts remain unreliable. Do not treat machine output as authoritative or infer actual backend integrations from the UI.

## Observations

| Approximate portion | Observed behavior | Evidence boundary |
| --- | --- | --- |
| Opening / first two minutes | Voice interface with microphone/end controls, speaking/listening states, and income information appearing on screen. | Visible in sampled frames. |
| 01:00–01:30 | User describes software engineering and ₹50,000 fixed monthly income; a follow-up asks about other earnings. | Supported by intelligible local audio translation, consistent with the user's account. |
| 01:30–02:00 | Delivery-app income initially ₹30,000, followed by a correction to ₹25,000; agent asks about the information shown on screen. | Supported by sampled translation and the user's account; exact UI recalculation timing was not measured. |
| Middle portion | Screens for loans, then cards, then household expenditure, family support and other expense categories. | Visible progression; low resolution prevents reliable extraction of every figure. |
| Around 07:00 onward | Dated repayment plan, ordered actions and subsequent review/continue interaction. | Visible in sampled frames. Audio samples suggest a smallest-balance-first explanation; details were not fully transcribed. |

The user separately describes Hindi conversation, informal borrowing and expense questioning. Those descriptions are useful context but are not additional independently verified video measurements.

## Implications for this design

- Preserve the connection between spoken facts and visible cards, while using an original interface and conversation flow.
- A correction should update a shared financial state; this review cannot establish how the demo implements that internally.
- Add explicit amount and timing uncertainty, protected spending preferences and dated cash-shortfall visibility as product requirements for our implementation.
- Do not use smallest balance alone to decide what to pay when essential cash needs and due dates conflict. Our proposed planner prioritises a feasible 30-day schedule before optional early payoff.
- The demo's Hindi output does not change the assignment's English-only requirement.
- A screen describing a report is not proof of an actual credit-bureau or Account Aggregator integration. Our prototype must accurately label its data sources.
