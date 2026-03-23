# Bank Files

Drop raw bank exports in this folder for local processing.

Notes:
- Raw bank files are ignored by git on purpose.
- Keep the original filenames from the bank when possible.
- Do not edit the PDFs manually before import.
- This folder is for local input only, not for published website assets.

Quick usage:
- Put new bank PDFs here.
- Run `python scripts/process_bank_files.py`
- Or double-click `run_bank_import.cmd` on Windows.

Automatic mode:
- Start `python scripts/watch_bank_files.py`
- Or double-click `run_bank_watch.cmd` on Windows.
- Then just drop new PDFs here and the local pipeline will parse and sync them automatically after the files finish copying.
