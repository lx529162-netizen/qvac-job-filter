# Risk log

Likelihood and impact: **low**, **medium**, **high**. Status: **open**, **mitigated**, **watching**. Reviewed 2026-11-11.

| # | Risk | Likelihood | Impact | Mitigation | Status |
|---|---|---|---|---|---|
| R1 | The model fits my test set better than new posts. I labelled the set and wrote the worked examples after seeing the failures. | medium | high | One-week side-by-side run on live posts, 3 to 9 November: quality on par with the cloud version, one clear mistake in 50 forwards. Keep labelling live posts and re-testing. | watching |
| R2 | A vacancy uses a title that is not in the role list, such as Implementation or Program Manager, and is skipped. | high | medium | The comparison week found one miss of this kind, "Руководитель ML-проектов", fixed in D10. Next: add Program, Implementation and Engagement Manager, then re-test. | open |
| R3 | Slow answers on CPU. A burst of posts queues up. | medium | low | The role pre-filter keeps calls to about 18 a day. With 4 OCPU: median 27 s. After the resize to 2 OCPU on 2026-11-10: 19 to 61 s per post. Next: measure with the schema off and with a cached prompt prefix. | watching |
| R4 | The Always Free quota for Ampere A1 dropped to 2 OCPU and 12 GB in June 2026. The server used 4 OCPU and 24 GB and could be reclaimed after the Free Trial. | high | high | Occurred: the Free Trial ended on 2026-11-10. The same day I resized the server to 2 OCPU and 12 GB, within the Always Free limit. Both bots kept running; about 6 GB of memory stays free. | mitigated |
| R5 | A new release of the young QVAC SDK or its dependencies breaks the install, as `bare-rpc` 0.1.0 did. | medium | medium | Pinned `bare-rpc`. Re-run both test sets before any SDK upgrade. | watching |
| R6 | The real-post test set holds personal data from resumes. | low | high | Kept only on the server, git-ignored, not published. Delete after the project. | mitigated |
| R7 | The model returns text that is not valid JSON. | low | low | JSON schema enforced at generation time. Invalid output is logged as UNCLEAR and not forwarded. | mitigated |
| R8 | Two processes use one Telegram session and Telegram logs both out. | low | high | Separate session for the QVAC version. Stop the bot before running helper scripts with the same session. | mitigated |
