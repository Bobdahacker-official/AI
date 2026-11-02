# Evaluation status

The current 0.5B checkpoint does not meet the requested commercial-quality target. The revised development check has 3 passes, 4 partial answers, and 5 failures in an agent assessment. Independent human review is still required. The initial run used different prompts, so its counts are not a controlled comparison.

Critical failures include recommending an interpolated SQL query, giving irrelevant incident-response instructions, omitting the requested object authorization test, and answering Yes when the user explicitly lacked authorization. Familiar SQL training prompts reproduce correctly, and the same fresh-prompt failure occurs before and after GPU adapter merging. The loading diagnostics are retained under reports/.

The raw outputs, criteria, training reports, and reviews are retained for audit and further development. Lower training loss is not evidence that these failures are fixed. The user has authorized evaluating Qwen2.5-1.5B using the resource policy in resource_policy.json; the existing checkpoint is preserved until a replacement is evaluated.
