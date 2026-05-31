#!/usr/bin/env python3
import os
import sys
import re
import argparse
import requests
import pdfplumber
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Try importing configuration, fallback to environment/empty if not present
try:
    import config
except ImportError:
    config = None

# Default configuration Fallbacks
GMAIL_APP_PASSWORD = getattr(config, "GMAIL_APP_PASSWORD", None) or os.environ.get("JOB_AGENT_GMAIL_APP_PASSWORD", "your_gmail_app_password")
INDEED_API_KEY = getattr(config, "INDEED_API_KEY", None) or os.environ.get("JOB_AGENT_INDEED_API_KEY", "your_rapidapi_key")
RAPIDAPI_HOST = getattr(config, "RAPIDAPI_HOST", "jsearch.p.rapidapi.com")
RAPIDAPI_URL = getattr(config, "RAPIDAPI_URL", "https://jsearch.p.rapidapi.com/search")

# Safely extract recipient list
raw_emails = getattr(config, "RECIPIENT_EMAILS", None)
if raw_emails:
    if isinstance(raw_emails, str):
        RECIPIENT_EMAILS = [raw_emails.strip()]
    elif isinstance(raw_emails, list):
        RECIPIENT_EMAILS = [email.strip() for email in raw_emails if email.strip()]
    else:
        RECIPIENT_EMAILS = []
else:
    # Try falling back to old EMAIL variable
    old_email = getattr(config, "EMAIL", None) or os.environ.get("JOB_AGENT_EMAIL", "your.email@gmail.com")
    RECIPIENT_EMAILS = [old_email]

# Use EMAIL as sender/authenticator if present, otherwise fallback to the first recipient email
SENDER_EMAIL = getattr(config, "EMAIL", None) or (RECIPIENT_EMAILS[0] if RECIPIENT_EMAILS else "your.email@gmail.com")

def find_resume_file(specified_path=None):
    """Finds the resume PDF file based on priorities."""
    if specified_path:
        if os.path.exists(specified_path):
            return specified_path
        print(f"Specified resume path '{specified_path}' not found. Searching defaults...")
    
    # Priority list of default names
    defaults = ["resume.pdf", "resume_sumitkate.pdf"]
    for default in defaults:
        if os.path.exists(default):
            return default
            
    # Search for any PDF in the current directory
    pdf_files = [f for f in os.listdir(".") if f.endswith(".pdf")]
    if pdf_files:
        print(f"No default resume file found. Auto-detected PDF: {pdf_files[0]}")
        return pdf_files[0]
        
    raise FileNotFoundError("Could not find any resume PDF file in the current directory.")

def extract_text_from_pdf(pdf_path):
    """Extracts all text from a PDF file using pdfplumber."""
    print(f"Reading resume: '{pdf_path}'...")
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        print(f"Extracted {len(text)} characters from resume.")
        return text
    except Exception as e:
        print(f"Error reading PDF file {pdf_path}: {e}")
        sys.exit(1)

def extract_candidate_name(text):
    """Attempts to extract the candidate's name from the top of the resume."""
    # Split text into lines and clean them
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return "Job Seeker"
        
    # Usually, the first line is the candidate's name
    for line in lines[:3]:
        # Filter out contact details, emails, links, or very long lines
        if len(line) < 30 and "@" not in line and "http" not in line and not any(kw in line.lower() for kw in ["curriculum", "resume", "vitae", "contact", "email", "phone"]):
            # Check if line contains letters and spaces
            if re.match(r"^[a-zA-Z\s\.\-]+$", line):
                return line
                
    return "Sumit Kate" # Fallback based on workspace context

def extract_skills(text):
    """Matches resume text against a dictionary of technical skills and categories."""
    skills_dict = {
        "Programming Languages": ["Python", "Java", "C\\+\\+", "C#", "TypeScript", "JavaScript", "Go", "Rust", "Ruby", "HTML", "CSS", "SQL", "PHP", "Swift", "Kotlin", "Scala"],
        "Frameworks & Libraries": ["React", "Angular", "Vue", "Next\\.js", "Node\\.js", "Express", "Django", "Flask", "FastAPI", "Spring Boot", "Hibernate", "PyTorch", "TensorFlow", "Keras", "Pandas", "NumPy", "Scikit-Learn", "Bootstrap", "Tailwind"],
        "Databases": ["PostgreSQL", "MySQL", "MongoDB", "Redis", "Cassandra", "SQLite", "Oracle", "DynamoDB"],
        "Tools & Platforms": ["Git", "Docker", "Kubernetes", "AWS", "Azure", "GCP", "Firebase", "Linux", "Jenkins", "Jira", "GitHub", "GitLab", "Heroku"],
        "Methodologies & Domains": ["Machine Learning", "Deep Learning", "Data Science", "Artificial Intelligence", "Full Stack", "Frontend", "Backend", "DevOps", "Cloud Computing", "API Development", "Microservices", "System Design", "Agile", "Scrum"]
    }
    
    extracted_skills = {}
    for category, keywords in skills_dict.items():
        matched = []
        for kw in keywords:
            # Match whole words, and handle special characters like C++ or Next.js
            if kw.endswith("+") or kw.endswith(".js"):
                pattern = rf"\b{kw}(?!\w)"
            else:
                pattern = rf"\b{kw}\b"
                
            if re.search(pattern, text, re.IGNORECASE):
                display_name = kw.replace("\\", "")
                matched.append(display_name)
        if matched:
            extracted_skills[category] = matched
            
    return extracted_skills

def extract_job_titles(text):
    """Matches resume text against common job titles and ranks by occurrence."""
    common_titles = [
        "Software Engineer", "Software Developer", "Frontend Engineer", "Frontend Developer",
        "Backend Engineer", "Backend Developer", "Full Stack Engineer", "Full Stack Developer",
        "Data Scientist", "Data Analyst", "Machine Learning Engineer", "DevOps Engineer",
        "Cloud Engineer", "Mobile Engineer", "Android Developer", "iOS Developer",
        "Product Manager", "Project Manager", "QA Engineer", "Systems Engineer",
        "Technical Lead", "Solutions Architect", "Database Administrator"
    ]
    
    matched_titles = []
    for title in common_titles:
        pattern = rf"\b{title}\b"
        matches = len(re.findall(pattern, text, re.IGNORECASE))
        if matches > 0:
            matched_titles.append((title, matches))
            
    # Sort by frequency of occurrence
    matched_titles.sort(key=lambda x: x[1], reverse=True)
    
    # Fallback to the top lines of the resume if no common titles match
    if not matched_titles:
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        for line in lines[:5]:
            if len(line) < 40 and not any(char.isdigit() for char in line) and "@" not in line and len(line) > 5:
                # Exclude candidate name
                name = extract_candidate_name(text)
                if line.lower() != name.lower():
                    matched_titles.append((line, 1))
                    
    # Return top 3 job titles
    return [title for title, count in matched_titles[:3]]

def get_mock_jobs(query, location):
    """Generates realistic mock jobs for testing or API fallbacks."""
    print(f"Generating mock Indeed jobs for '{query}' in '{location}'...")
    
    # Generic mock description templates to match skills in relevance scoring
    jobs = [
        {
            "title": f"Senior {query}",
            "company": "Google India",
            "location": "Bangalore, Karnataka, India",
            "salary": "₹25,00,000 - ₹35,00,000 a year",
            "url": "https://indeed.com/rc/clk?jk=mockgoog123",
            "description": "We are seeking a Senior Developer experienced in Python, React, and AWS Cloud. Strong expertise in Docker, Git, SQL, and microservices is required. Work with machine learning teams to design systems.",
            "source": "Mock (API Fallback)"
        },
        {
            "title": f"{query} - Full Stack",
            "company": "Flipkart",
            "location": "Bangalore, Karnataka, India",
            "salary": "₹18,00,000 - ₹24,00,000 a year",
            "url": "https://indeed.com/rc/clk?jk=mockflip456",
            "description": "Join our engineering team building high-scale applications. Required skills include JavaScript, TypeScript, Next.js, Node.js, Express, MongoDB, and PostgreSQL. Familiarity with Kubernetes is a plus.",
            "source": "Mock (API Fallback)"
        },
        {
            "title": f"Junior {query}",
            "company": "Tata Consultancy Services (TCS)",
            "location": "Pune, Maharashtra, India",
            "salary": "₹6,00,000 - ₹8,50,000 a year",
            "url": "https://indeed.com/rc/clk?jk=mocktcs789",
            "description": "Entry-level position for enthusiastic developers. Candidates should know Java, Spring Boot, Git, HTML, CSS, and MySQL. Good problem solving skills and familiarity with agile software development.",
            "source": "Mock (API Fallback)"
        },
        {
            "title": f"Lead {query}",
            "company": "Microsoft India",
            "location": "Hyderabad, Telangana, India",
            "salary": "Not disclosed",
            "url": "https://indeed.com/rc/clk?jk=mockmsft999",
            "description": "Lead a team of engineers building cloud services on Azure. Technical skills: Python, Go, GCP/AWS/Azure, system design, API development, Linux, and Kubernetes. Excellent communication and project management.",
            "source": "Mock (API Fallback)"
        },
        {
            "title": f"{query} (AI/ML Specialist)",
            "company": "Fractal Analytics",
            "location": "Mumbai, Maharashtra, India",
            "salary": "₹15,00,000 - ₹22,00,000 a year",
            "url": "https://indeed.com/rc/clk?jk=mockfrac111",
            "description": "Build production Machine Learning, Deep Learning, and Artificial Intelligence solutions. Requirements: Python, PyTorch, TensorFlow, Pandas, NumPy, Scikit-Learn, and cloud deployment.",
            "source": "Mock (API Fallback)"
        },
        {
            "title": f"{query} - DevOps & Cloud",
            "company": "Wipro",
            "location": "Gurgaon, Haryana, India",
            "salary": "₹12,00,000 - ₹16,00,000 a year",
            "url": "https://indeed.com/rc/clk?jk=mockwipr222",
            "description": "Deploy, monitor, and scale cloud applications. Skills required: Docker, Kubernetes, Jenkins, AWS, Azure, Linux, Bash scripting, and Git. Automation and CI/CD development experience.",
            "source": "Mock (API Fallback)"
        }
    ]
    return jobs

def search_indeed_jobs(query, api_key, host, url_base):
    """Queries the Job Search API on RapidAPI and normalizes the output."""
    if not api_key or api_key == "your_rapidapi_key":
        return get_mock_jobs(query, "India")
        
    # Ensure correct URL format
    url = url_base if url_base.startswith("http") else f"https://{url_base}"
    
    # Setup headers
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": host
    }
    
    # Check if host is JSearch or indeed11 to set query param key
    param_key = "query" if "jsearch" in host.lower() else "keyword"
    
    # Setup standard parameters
    params = {
        param_key: query,
        "offset": "0"
    }
    
    try:
        print(f"Querying RapidAPI ({host}) for '{query}'...")
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        # If the root URL returns 404, try automatically appending '/search'
        if response.status_code == 404 and not url.endswith("/search"):
            search_url = url.rstrip("/") + "/search"
            print(f"Received 404. Attempting query on alternative endpoint: {search_url}...")
            response = requests.get(search_url, headers=headers, params=params, timeout=15)
            
        response.raise_for_status()
        data = response.json()
        
        return normalize_api_response(data)
    except Exception as e:
        print(f"API query failed ({e}). Falling back to mock data.")
        return get_mock_jobs(query, "India")

def normalize_api_response(data):
    """Safely normalizes varied JSON responses from JSearch and Indeed scrapers."""
    normalized_list = []
    
    # The API might return a list directly, or wrap it under keys like 'results', 'data', 'jobs', etc.
    raw_jobs = []
    if isinstance(data, list):
        raw_jobs = data
    elif isinstance(data, dict):
        for key in ["results", "data", "jobs", "jobList", "listings"]:
            if key in data and isinstance(data[key], list):
                raw_jobs = data[key]
                break
        # If no lists found, but the dict itself represents a single job
        if not raw_jobs and ("title" in data or "job_title" in data):
            raw_jobs = [data]
            
    for item in raw_jobs:
        if not isinstance(item, dict):
            continue
            
        # Extract title
        title = item.get("job_title") or item.get("title") or item.get("jobTitle") or item.get("jobtitle") or "Unknown Title"
        
        # Extract company
        company = (item.get("company_name") or item.get("company") or item.get("companyName") or 
                   item.get("companyname") or item.get("employer_name") or item.get("employerName") or "Unknown Company")
        
        # Extract location
        location = item.get("job_location") or item.get("location") or item.get("jobLocation") or item.get("formattedLocation") or ""
        if not location:
            loc_parts = [item.get("job_city"), item.get("job_state"), item.get("job_country")]
            location = ", ".join([p for p in loc_parts if p]) or "India"
            
        # Extract salary
        salary = item.get("salary") or item.get("salaryText") or item.get("salary_text") or item.get("salary_range") or "Not disclosed"
        if isinstance(salary, dict):
            # Sometimes salary is nested (min, max, currency)
            min_val = salary.get("min") or salary.get("minimum")
            max_val = salary.get("max") or salary.get("maximum")
            curr = salary.get("currency") or "INR"
            if min_val and max_val:
                salary = f"{curr} {min_val} - {max_val}"
            elif min_val:
                salary = f"From {curr} {min_val}"
            else:
                salary = "Not disclosed"
        elif (not salary or salary == "Not disclosed") and item.get("job_min_salary") and item.get("job_max_salary"):
            min_val = item.get("job_min_salary")
            max_val = item.get("job_max_salary")
            curr = item.get("job_salary_currency") or "INR"
            period = item.get("job_salary_period") or "year"
            salary = f"{curr} {min_val} - {max_val} a {period.lower()}"
                
        # Extract URL & ensure it is an absolute link
        url = (item.get("job_url") or item.get("url") or item.get("jobUrl") or 
               item.get("apply_link") or item.get("link") or item.get("job_apply_link") or "")
        if url and url.startswith("/"):
            url = f"https://www.indeed.com{url}"
            
        # Extract description / summary for relevance scoring
        description = (item.get("description") or item.get("summary") or item.get("snippet") or 
                       item.get("jobDescription") or item.get("job_description") or "")
        
        normalized_list.append({
            "title": title.strip(),
            "company": company.strip(),
            "location": location.strip(),
            "salary": str(salary).strip(),
            "url": url.strip(),
            "description": description.strip(),
            "source": "Job Search API"
        })
        
    return normalized_list

def calculate_relevance_score(job, skills_flattened, target_titles):
    """Calculates relevance score based on resume keyword matching."""
    score = 0
    title_lower = job["title"].lower()
    desc_lower = job["description"].lower()
    
    # 1. Match skills in the job title (highly weighted)
    for skill in skills_flattened:
        if skill.lower() in title_lower:
            score += 5
            
    # 2. Match skills in the job description (moderately weighted)
    for skill in skills_flattened:
        # Match with boundary to avoid partial words
        pattern = rf"\b{re.escape(skill.lower())}\b"
        if re.search(pattern, desc_lower):
            score += 1
            
    # 3. Match search query job titles (weighted)
    for target in target_titles:
        if target.lower() in title_lower:
            score += 8
            
    return score

def rank_and_deduplicate_jobs(jobs_list, skills_list, target_titles):
    """Scores, filters, deduplicates, and picks top 10 jobs."""
    # Flatten the skills list
    skills_flattened = []
    for category_skills in skills_list.values():
        skills_flattened.extend(category_skills)
        
    scored_jobs = []
    seen_keys = set() # To deduplicate based on title + company
    
    for job in jobs_list:
        # Ensure it has India in location
        if "india" not in job["location"].lower() and "in" not in job["location"].lower().split():
            # Skip if it is clearly not in India
            continue
            
        dedup_key = f"{job['title'].lower()}|{job['company'].lower()}"
        if dedup_key in seen_keys:
            continue
            
        seen_keys.add(dedup_key)
        score = calculate_relevance_score(job, skills_flattened, target_titles)
        
        job_copy = job.copy()
        job_copy["relevance_score"] = score
        scored_jobs.append(job_copy)
        
    # Sort by score descending
    scored_jobs.sort(key=lambda x: x["relevance_score"], reverse=True)
    return scored_jobs[:10]

def build_html_email(candidate_name, skills, target_titles, jobs):
    """Generates a responsive and beautifully formatted HTML email report."""
    
    # Prepare skills HTML chips
    skills_html = ""
    for category, category_skills in skills.items():
        chips = "".join([f'<span style="display:inline-block; background-color:#eef2ff; color:#4f46e5; border:1px solid #c7d2fe; padding:4px 10px; border-radius:16px; margin:4px; font-size:12px; font-family:\'Segoe UI\',Roboto,sans-serif;">{s}</span>' for s in category_skills])
        skills_html += f"""
        <div style="margin-bottom:12px;">
            <strong style="color:#1e293b; font-family:\'Segoe UI\',Roboto,sans-serif; font-size:13px; display:block; margin-bottom:4px;">{category}:</strong>
            {chips}
        </div>
        """
        
    # Prepare jobs list HTML
    jobs_html = ""
    if not jobs:
        jobs_html = """
        <div style="text-align:center; padding:40px; background:#f8fafc; border-radius:8px; border:1px dashed #cbd5e1; color:#64748b;">
            <p style="font-size:16px; margin:0; font-family:\'Segoe UI\',Roboto,sans-serif;">No matching jobs found in India. Try updating configuration or checking connection.</p>
        </div>
        """
    else:
        for idx, job in enumerate(jobs):
            # Display a nice tag for source (Mock vs Live)
            source_color = "#3b82f6" if "Mock" not in job["source"] else "#64748b"
            source_tag = f'<span style="background-color:{source_color}10; color:{source_color}; border:1px solid {source_color}30; padding:2px 8px; border-radius:12px; font-size:11px; float:right; font-family:\'Segoe UI\',Roboto,sans-serif;">{job["source"]}</span>'
            
            # Show a salary badge if available
            salary_html = ""
            if job["salary"] and job["salary"].lower() != "not disclosed" and job["salary"].lower() != "none":
                salary_html = f"""
                <span style="display:inline-block; background-color:#f0fdf4; color:#166534; border:1px solid #bbf7d0; padding:3px 8px; border-radius:4px; font-size:12px; margin-top:8px; font-family:\'Segoe UI\',Roboto,sans-serif; font-weight:bold;">
                    {job["salary"]}
                </span>
                """
                
            apply_btn = ""
            if job["url"]:
                apply_btn = f"""
                <table cellspacing="0" cellpadding="0" style="margin-top:14px;">
                    <tr>
                        <td align="center" width="120" height="34" bgcolor="#4f46e5" style="border-radius:6px;">
                            <a href="{job["url"]}" target="_blank" style="font-family:\'Segoe UI\',Roboto,sans-serif; font-size:13px; color:#ffffff; text-decoration:none; line-height:34px; width:120px; display:inline-block; font-weight:bold; text-align:center;">
                                Apply Indeed &rarr;
                            </a>
                        </td>
                    </tr>
                </table>
                """
                
            jobs_html += f"""
            <div style="background-color:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:18px; margin-bottom:16px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                {source_tag}
                <div style="font-size:12px; font-weight:bold; color:#4f46e5; text-transform:uppercase; letter-spacing:0.5px; font-family:\'Segoe UI\',Roboto,sans-serif; margin-bottom:4px;">Match #{idx+1} &bull; Score: {job.get('relevance_score', 0)}</div>
                <h3 style="margin:0 0 6px 0; color:#0f172a; font-size:18px; font-family:\'Segoe UI\',Roboto,sans-serif;">{job["title"]}</h3>
                <div style="color:#334155; font-size:14px; font-family:\'Segoe UI\',Roboto,sans-serif; font-weight:500; margin-bottom:6px;">{job["company"]}</div>
                <div style="color:#64748b; font-size:13px; font-family:\'Segoe UI\',Roboto,sans-serif; display:inline-block; margin-right:12px;">
                    <span style="font-size:14px;">📍</span> {job["location"]}
                </div>
                {salary_html}
                <p style="color:#475569; font-size:13px; font-family:\'Segoe UI\',Roboto,sans-serif; line-height:1.5; margin:12px 0 0 0; background-color:#f8fafc; padding:10px; border-radius:4px; border-left:3px solid #cbd5e1;">
                    {job["description"][:280]}...
                </p>
                {apply_btn}
            </div>
            """

    # Assemble full email body with modern CSS and layout
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Your Curated Job Matches</title>
    </head>
    <body style="background-color:#f1f5f9; margin:0; padding:0; -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale;">
        <table align="center" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width:650px; margin: 20px auto; background-color:#f1f5f9; padding: 0 10px;">
            <tr>
                <td>
                    <!-- Elegant Header Card -->
                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%); border-top-left-radius:12px; border-top-right-radius:12px; overflow:hidden;">
                        <tr>
                            <td style="padding:35px 25px; text-align:center;">
                                <div style="display:inline-block; background-color:rgba(255,255,255,0.1); border-radius:50%; width:50px; height:50px; line-height:50px; font-size:24px; color:#ffffff; margin-bottom:12px; text-align:center; font-family:\'Segoe UI\',Roboto,sans-serif;">🤖</div>
                                <h1 style="color:#ffffff; margin:0; font-size:26px; font-family:\'Segoe UI\',Roboto,sans-serif; font-weight:800; letter-spacing:-0.5px;">Antigravity Job Agent</h1>
                                <p style="color:#cbd5e1; margin:6px 0 0 0; font-size:14px; font-family:\'Segoe UI\',Roboto,sans-serif;">Personalized indeed search for India</p>
                            </td>
                        </tr>
                    </table>

                    <!-- Profile Analysis Card -->
                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#ffffff; border-bottom-left-radius:0px; border-bottom-right-radius:0px; border:1px solid #e2e8f0; border-top:none;">
                        <tr>
                            <td style="padding:24px;">
                                <h2 style="margin:0 0 16px 0; color:#0f172a; font-size:18px; font-family:\'Segoe UI\',Roboto,sans-serif; border-bottom:2px solid #f1f5f9; padding-bottom:8px;">Resume Profile Summary</h2>
                                <p style="color:#334155; font-size:14px; font-family:\'Segoe UI\',Roboto,sans-serif; margin:0 0 12px 0;">
                                    <strong>Candidate:</strong> {candidate_name}<br>
                                    <strong>Target Roles:</strong> {", ".join(target_titles)}
                                </p>
                                {skills_html}
                            </td>
                        </tr>
                    </table>

                    <!-- Separator -->
                    <div style="height:20px;"></div>

                    <!-- Job Listings Header -->
                    <div style="font-family:\'Segoe UI\',Roboto,sans-serif; font-size:16px; font-weight:bold; color:#1e293b; margin-bottom:12px; padding-left:4px;">
                        🎯 Top 10 Job Matches
                    </div>

                    <!-- Job Cards -->
                    {jobs_html}

                    <!-- Footer -->
                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="padding:24px 10px; text-align:center; color:#64748b; font-size:12px; font-family:\'Segoe UI\',Roboto,sans-serif;">
                        <tr>
                            <td>
                                <p style="margin:0 0 6px 0;">This email was automatically compiled by your automated Job Agent.</p>
                                <p style="margin:0;">&copy; 2026 Antigravity Job Agent. All rights reserved.</p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    return html

def send_email(subject, html_content, to_email, sender_email, app_password):
    """Sends a nicely formatted HTML email via Gmail SMTP using SSL or STARTTLS."""
    if not to_email or to_email == "your.email@gmail.com":
        print("WARNING: Recipient email is not configured in config.py.")
        return False
        
    if not app_password or app_password == "your_gmail_app_password":
        print("WARNING: Gmail App Password is not configured in config.py.")
        return False
        
    # Create message container
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = to_email
    
    # Attach HTML content
    part = MIMEText(html_content, 'html')
    msg.attach(part)
    
    try:
        print(f"Connecting to Gmail SMTP server to send email to {to_email}...")
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            print(f"Logging into SMTP server as {sender_email}...")
            server.login(sender_email, app_password)
            print(f"Sending email to {to_email}...")
            server.sendmail(sender_email, to_email, msg.as_string())
            print(f"Email sent successfully to {to_email}!")
            return True
    except Exception as e:
        print(f"Error sending email via SMTP_SSL to {to_email}: {e}")
        print("Attempting fallback using STARTTLS on port 587...")
        try:
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls(context=context)
                server.login(sender_email, app_password)
                server.sendmail(sender_email, to_email, msg.as_string())
                print(f"Email sent successfully to {to_email} via STARTTLS!")
                return True
        except Exception as fallback_e:
            print(f"STARTTLS fallback failed for {to_email}: {fallback_e}")
            return False

def main():
    parser = argparse.ArgumentParser(description="Antigravity Job Agent - Scan resume & fetch matching jobs from Indeed.")
    parser.add_argument("--resume", type=str, help="Path to resume PDF file")
    parser.add_argument("--dry-run", action="store_true", help="Run without sending emails or calling Live API if keys are missing")
    parser.add_argument("--output", type=str, default="job_matches.html", help="Path to save the generated HTML email preview")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("              ANTIGRAVITY JOB AGENT ACTIVE              ")
    print("=" * 60)
    
    # 1. Resolve resume path and parse text
    try:
        resume_path = find_resume_file(args.resume)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
        
    text = extract_text_from_pdf(resume_path)
    
    # 2. Extract profile details
    candidate_name = extract_candidate_name(text)
    skills = extract_skills(text)
    target_titles = extract_job_titles(text)
    
    print("\n--- Profile Analysis Results ---")
    print(f"Candidate Name : {candidate_name}")
    print(f"Extracted Roles: {', '.join(target_titles) if target_titles else 'None detected'}")
    print("Extracted Skills:")
    for cat, items in skills.items():
        print(f"  * {cat}: {', '.join(items)}")
    print("-" * 32)
    
    if not target_titles:
        target_titles = ["Software Developer"] # absolute fallback
        print("No job titles detected. Defaulting search query to 'Software Developer'")
        
    # 3. Query Jobs from Indeed for each target job title
    all_raw_jobs = []
    
    # For testing in dry-run mode, if no key is configured, force mock jobs
    use_mock = args.dry_run and (not INDEED_API_KEY or INDEED_API_KEY == "your_rapidapi_key")
    
    for title in target_titles:
        search_query = f"{title} India"
        if use_mock:
            jobs = get_mock_jobs(search_query, "India")
        else:
            jobs = search_indeed_jobs(search_query, INDEED_API_KEY, RAPIDAPI_HOST, RAPIDAPI_URL)
        all_raw_jobs.extend(jobs)
        
    # 4. Rank and filter to Top 10
    top_jobs = rank_and_deduplicate_jobs(all_raw_jobs, skills, target_titles)
    
    print(f"\nFound {len(all_raw_jobs)} total job listings. Filtered and ranked to top {len(top_jobs)} matches in India.")
    for idx, j in enumerate(top_jobs):
        print(f" {idx+1}. [{j['source']}] {j['title']} at {j['company']} ({j['location']}) - Score: {j.get('relevance_score', 0)}")
        
    # 5. Build HTML Email Content
    html_content = build_html_email(candidate_name, skills, target_titles, top_jobs)
    
    # 6. Save locally for preview
    output_path = args.output
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"\nHTML email preview saved locally to '{output_path}'. Open this in a browser to inspect the design.")
    except Exception as e:
        print(f"Warning: Could not save local HTML preview: {e}")
        
    # 7. Send the Email
    if args.dry_run:
        print("\nDry-run mode active. Skipping email transmission.")
        print("Set up credentials in config.py and run without --dry-run to send actual emails.")
    else:
        subject = f"🔔 Top {len(top_jobs)} Job Openings in India for {candidate_name}"
        success_count = 0
        total_recipients = len(RECIPIENT_EMAILS)
        print(f"\nSending email notifications to {total_recipients} recipient(s)...")
        for recipient in RECIPIENT_EMAILS:
            email_sent = send_email(subject, html_content, recipient, SENDER_EMAIL, GMAIL_APP_PASSWORD)
            if email_sent:
                success_count += 1
                
        if success_count == total_recipients:
            print(f"\nSuccess! All {total_recipients} email notifications sent.")
        elif success_count > 0:
            print(f"\nPartial success: {success_count}/{total_recipients} emails sent successfully.")
        else:
            print("\nFailed to send any email. Check your SMTP settings and Gmail App Password in config.py.")
            print(f"You can review the generated jobs in '{output_path}'.")
            
    print("=" * 60)

if __name__ == "__main__":
    main()
