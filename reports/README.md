# Astheral conversation evidence

These files contain actual generated responses, including failures. None of the replies were replaced with reference answers.

- `astheral-phrasing-api.json`: the selected step-3090 checkpoint fixes the previously failing greeting/name and greeting/dinner exchanges and answers an introduction request through the HTTP endpoint.
- `astheral-25-turn-api.json`: 25 user turns and 25 generated replies through the real HTTP endpoint with a 32-token reply budget.
- `astheral-25-turn-ui.json`: the same 25 user turns through HTTP with the browser's 64-token reply budget.
- `astheral-25-turn-baseline.json`: the earlier selected step-1190 checkpoint on the same prompts, using direct model inference.

The HTTP sessions completed all 25 user turns without malformed-history errors. That is protocol evidence, not evidence of 25 coherent replies. Later topic changes, arithmetic, and name recall still fail frequently. The current selected checkpoint remains a narrow conversational model.

Keyword diagnostics were recomputed using the stricter version-2 checker; the older substring flags are retained as `previous_substring_proxy_match`. Raw responses were not changed. The stricter counts are 2/25 for the baseline and 5/25 for each HTTP session. Even these matches are not correctness scores: for example, mentioning music while asking about reading still contains a topic keyword. Read the full responses.

The earlier step-1190 selected weights are retained locally as `runs/astheral-conversation/selected-before-phrasing.pt`. Step 3090 is selected for serving. The separate decoder-training trial and recurring 25-turn assessments continue under `runs/astheral-decoder/`; a new checkpoint is not selected solely because its loss or keyword count improves.
