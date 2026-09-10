# Engineering workflow

## 1. Understand the brief

Read the full assignment and relevant reference material. Capture requirements, constraints, and acceptance checks in `requirements.md`. Separate mandatory scope from optional ideas.

## 2. Choose an approach

Identify the smallest complete user flow and the riskiest assumption. Compare plausible stacks against assignment fit, familiarity, implementation effort, testing, and deployment needs. Pipecat and Daily are mandatory. Discuss tradeoffs without writing or summarising the candidate's journal decisions.

## 3. Build incrementally

Implement a working flow through the necessary layers. Keep configuration reproducible, external dependencies explicit, and simulated behavior visible. Add further flows in small, reviewable changes.

## 4. Verify behavior

Choose tests that establish correctness for the actual requirements. Cover relevant boundary and failure cases, and inspect the complete user flow. Record commands and results; distinguish automated tests, manual checks, and unverified assumptions.

## 5. Prepare submission

Recheck the original brief and acceptance mapping. Document setup, design rationale, limitations, and required submission artifacts. Verify the setup instructions where feasible. Keep personal journal writing with the candidate.

Specific commands, directory layout, and CI checks will be added when the stack is selected.

