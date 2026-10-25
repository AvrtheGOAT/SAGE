# SAGE on Nodus

The missed-reminder **pattern check** runs as a Nodus function that the Flask backend calls.
It compares each elder's recent weeks with **their own first four weeks** (missed reminders, late replies,
reply delay, how often SAGE had to repeat a reminder) and flags two weeks in a row above normal.
The ML model (`flagging_model/`) gives the main verdict; this is the second, independent check.

## Run it (from C:\SAGE, venv active)
1. `pip install nodus-compute` then `nodus login` (the account where the credits were redeemed)
2. `nodus run nodus_jobs/hello.py` → prints **49** (proves login + credits)
3. `nodus run nodus_jobs/sage_nodus.py` → prints a result with `"status": "flag"` for the demo history
4. `nodus deploy nodus_jobs/sage_nodus.py` → keeps it running so the backend can call it
5. `backend\.env`: `NODUS_ENABLED=1`, then restart `python app.py`

The backend window then prints e.g. `[nodus] pattern check for sage-home-01: ran on nodus in 1840 ms -> flag`,
and the dashboard's Memory & routine card shows **"ran on Nodus"**.

## If Nodus isn't reachable
The backend runs the same `pattern_check_logic()` locally and the dashboard says **"ran locally"**
(hover it to see why). Nothing breaks. Set `NODUS_ENABLED=0` for a fully offline demo.

## Evidence for the judges
- `GET /api/nodus/status` → where the last check ran + total checks run on Nodus
- Every check is stored in the `nodus_runs` collection (ran_on, duration, result)
- Keep the Nodus dashboard / logs open during the demo (`nodus --help` lists the log commands)

No GPU is requested on purpose: SAGE doesn't need one and GPUs burn credits fast.
If `nodus run` complains about a missing GPU or another option, check `nodus --help` or ask the Nodus team.
