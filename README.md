# Antigravity Job Agent 🤖💼

An automated, AI-driven job search assistant that parses your resume PDF, extracts technical skills and target roles, queries the JSearch API via RapidAPI to search for matches in India, ranks the positions using a custom skill-matching relevance scoring algorithm, and emails a premium HTML report to multiple recipients daily.

---

## Key Features
- 📄 **Resume Parsing**: Automatically extracts candidate details, technical skill categories, and roles from PDF files using `pdfplumber`.
- 🔍 **JSearch API Integration**: Leverages JSearch API via RapidAPI for high-fidelity job searching across India.
- 🎯 **Relevance Scoring & Ranking**: Computes an overlap score matching resume skills to job descriptions and target titles to pick the top 10 positions.
- 📨 **Multi-Recipient Email Delivery**: Builds a responsive, modern HTML newsletter dashboard and distributes individual emails to a configured list of recipients via Gmail SMTP.
- 🧪 **Dry-run Mode**: Test parsing and email HTML generation locally without sending emails or using active API key credits.

---

## Tech Stack
- **Core Language**: Python 3
- **Libraries**:
  - `pdfplumber`: PDF text extraction.
  - `requests`: REST API requests to RapidAPI.
  - `smtplib` & `ssl`: Secure email transmission using Gmail SMTP over SSL/STARTTLS.

---

## Project Structure
```text
job-agent/
│
├── config.py           # User credentials, recipient emails list, and API keys (git ignored)
├── job_agent.py        # Core application script containing parsing, API client, & SMTP logic
├── requirements.txt    # Required python dependencies
├── .gitignore          # Git exclusion rules
└── README.md           # Project documentation and setup guide
```

---

## Setup & Installation

### 1. Prerequisites
- **Python 3.8+** installed.
- **Gmail Account**: You will need a **Gmail App Password** (regular password will not work).
- **RapidAPI Subscription**: A subscription to the JSearch API on RapidAPI to get your `X-RapidAPI-Key`.

### 2. Environment Setup
Create a virtual environment and install the required dependencies:

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configuration Setup
Create a `config.py` file in the root directory (based on `config.py` structure):

```python
# List of recipient Gmail addresses where you want to receive the alerts
RECIPIENT_EMAILS = [
    "example1@gmail.com",
    "example2@gmail.com"
]

# Your Gmail App Password (16 characters, no spaces)
GMAIL_APP_PASSWORD = "your_gmail_app_password"

# Your JSearch API (RapidAPI) Key
INDEED_API_KEY = "your_rapidapi_key"

# JSearch API Configuration
RAPIDAPI_HOST = "jsearch.p.rapidapi.com"
RAPIDAPI_URL = "https://jsearch.p.rapidapi.com/search"
```

---

## Running the Agent

### Local Execution
To run the job agent and send live emails:
```bash
python3 job_agent.py
```

To run a test in **Dry-Run** mode (uses mock jobs and skips email transmission, saving results to `job_matches.html`):
```bash
python3 job_agent.py --dry-run
```

### Automating Daily Reports (Cron Setup)
You can automate this script to run daily using a standard Unix `cron` job.

1. Open your crontab configuration:
   ```bash
   crontab -e
   ```
2. Add a line to execute the script daily (e.g., at 9:00 AM). Make sure to use absolute paths to your virtual environment's Python binary and script:
   ```cron
   0 9 * * * /path/to/job-agent/venv/bin/python3 /path/to/job-agent/job_agent.py >> /path/to/job-agent/job_agent.log 2>&1
   ```
