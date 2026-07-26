# Desktop license-plate recognition

Python desktop application for license-plate recognition, local history and
database workflows, and optional Telegram notifications and streaming.

## Local setup

1. Install the native DTK LPR/video libraries required by `DTKLPR5.py` and
   `DTKVID.py`.
2. Create an isolated Python environment and install the packages imported by
   the application.
3. Copy the environment template and fill it locally:

   ```bash
   cp .env.example .env
   ```

4. Keep database and Telegram session paths outside version control, then run:

   ```bash
   python3 main.py
   ```

The empty values in `.env.example` are intentional. Telegram integration is
optional, but the application must be configured for the features you enable.

## Security

Never commit `.env`, Telegram session files, local databases, or logs. Removing
a secret from the current revision does not remove it from Git history. Treat
any credential or session that was previously committed as exposed and replace
it through the relevant provider before reuse.
