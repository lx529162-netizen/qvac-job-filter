# Risk log

Likelihood and impact: **low**, **medium**, **high**. Status: **open**, **mitigated**, **watching**. Reviewed 2026-11-04.

| # | Risk | Likelihood | Impact | Mitigation | Status |
|---|---|---|---|---|---|
| R1 | The model fits my test set better than new posts. I labelled the set and wrote the worked examples after seeing the failures. | medium | high | One-week side-by-side run on live posts. Label new posts from that week and re-test. | open |
| R2 | A vacancy uses a title that is not in the role list, such as Implementation or Program Manager, and is skipped. | high | medium | Same list as the cloud version during the comparison week. Extend it after the week, then re-test. | open |
| R3 | Slow answers on CPU, about 40 s per post that reaches the model. A burst of posts queues up. | medium | low | The role pre-filter cuts model calls by about 80%. Next: measure with the schema off and with a cached prompt prefix. | mitigated |
| R4 | The Always Free quota for Ampere A1 dropped to 2 OCPU and 12 GB in June 2026. The server uses 4 OCPU and 24 GB and may be billed or stopped. | high | high | Check billing. If needed, resize to 2 OCPU and 12 GB: the 4B model fits, answers get slower. | open |
| R5 | A new release of the young QVAC SDK or its dependencies breaks the install, as `bare-rpc` 0.1.0 did. | medium | medium | Pinned `bare-rpc`. Re-run both test sets before any SDK upgrade. | watching |
| R6 | The real-post test set holds personal data from resumes. | low | high | Kept only on the server, git-ignored, not published. Delete after the project. | mitigated |
| R7 | The model returns text that is not valid JSON. | low | low | JSON schema enforced at generation time. Invalid output is logged as UNCLEAR and not forwarded. | mitigated |
| R8 | Two processes use one Telegram session and Telegram logs both out. | low | high | Separate session for the QVAC version. Stop the bot before running helper scripts with the same session. | mitigated |
