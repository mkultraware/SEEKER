# SEEKER
# GPU Price Sniper

Automated tool for tracking GPU prices (RTX 5090, 5080, 4090) across major Swedish retailers like Webhallen, Inet, Komplett, and NetOnNet.



## Features
- **Multi-Platform:** Optimized scripts for Windows (`MKULTRA.py`) and macOS (`MACULTRA.py`).
- **Anti-Detection:** Uses `curl_cffi` and randomized headers to bypass bot protections.
- **Dynamic Content:** Integrates `Playwright` to scrape JavaScript-heavy sites.
- **Alerts:** Sends email notifications via SMTP when price targets are met. Make sure your information is entered here otherwise no notifications will be sent. 

## Setup
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install


Configure your email settings in the script or use environment variables.

Run the script:
python MKULTRA_Sanitized.py

Disclaimer
This tool was made for the authors learning purposes.
