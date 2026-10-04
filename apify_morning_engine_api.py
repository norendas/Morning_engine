import os
import requests
import json
import csv
import re
from datetime import datetime

# 1. Configuration & Credentials
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")
HEADERS = {"Content-Type": "application/json"}

BENCH_PROFILES = [
    {
        "dev_id": "DEV-REACT-NODE",
        "tech_stack": "React / Node.js",
        "job_keyword": "Senior React Engineer OR Full Stack Node",
        "target_titles": '("VP of Engineering" OR "Chief Technology Officer" OR "Head of Engineering")'
    },
    {
        "dev_id": "DEV-AI-PYTHON",
        "tech_stack": "Python / AI / ML",
        "job_keyword": "Senior Python Engineer OR AI Engineer",
        "target_titles": '("CTO" OR "VP of Engineering" OR "Head of AI")'
    }
]

# 2. Helper Functions
def clean_job_title(raw_title):
    """Strips corporate tags, requisition codes, and parentheses."""
    if not raw_title:
        return "Software Engineer"
    cleaned = re.sub(r'\(.*?\)', '', raw_title)
    cleaned = cleaned.split('-')[0].split('|')[0].strip()
    return cleaned if cleaned else "Software Engineer"

def generate_option1_hook(company, raw_title, bench_stack, client_name="Daniel's engineering team at TLVTech"):
    clean_title = clean_job_title(raw_title)
    return (
        f"Saw {company} is looking to fill a {clean_title} seat across {bench_stack}. "
        f"If the 60-day recruitment cycle is bottlenecking roadmap velocity, {client_name} "
        f"has pre-vetted pods in that exact stack ready to plug into sprints right now. "
        f"Open to seeing a 2-minute snapshot of their architecture work?"
    )

def run_apify_actor(actor_id, run_input):
    """Triggers an Apify actor and returns dataset items."""
    if not APIFY_TOKEN:
        print("[!] ERROR: APIFY_TOKEN environment variable is missing.")
        return []
    
    run_url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items?token={APIFY_TOKEN}"
    try:
        response = requests.post(run_url, headers=HEADERS, json=run_input, timeout=180)
        if response.status_code in [200, 201]:
            return response.json()
        print(f"[!] Apify API Error ({actor_id}): {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[!] Request Exception calling {actor_id}: {e}")
    return []

# 3. Scraping Functions
def get_hiring_companies(keyword, max_companies=20):
    """Scrapes LinkedIn jobs for companies actively hiring for target skills."""
    print(f"--> [Step 1] Sourcing hiring companies for: '{keyword}'...")
    run_input = {
        "keywords": keyword,
        "location": "United States",
        "datePosted": "past-week",
        "maxItems": max_companies
    }
    jobs = run_apify_actor("logical_scrapers~linkedin-jobs-scraper", run_input)
    
    unique_companies = []
    seen = set()
    for job in jobs:
        c_name = job.get("company")
        if c_name and c_name.strip() and c_name not in seen:
            seen.add(c_name)
            unique_companies.append({
                "company": c_name.strip(),
                "job_title": job.get("title", "Software Engineer"),
                "job_url": job.get("jobUrl") or job.get("sourceUrl", "")
            })
    return unique_companies

def find_technical_decision_maker(company_name, target_titles_query):
    """Executes a targeted Google X-Ray search to locate the engineering lead."""
    search_query = f'site:linkedin.com/in "{company_name}" {target_titles_query} -jobs'
    run_input = {
        "queries": search_query,
        "maxPagesPerQuery": 1,
        "resultsPerPage": 3
    }
    results = run_apify_actor("apify~google-search-scraper", run_input)
    
    if results and isinstance(results, list) and len(results) > 0:
        organic = results[0].get("organicResults", [])
        for res in organic:
            url = res.get("url", "")
            if "linkedin.com/in/" in url:
                raw_title = res.get("title", "")
                name = raw_title.split("-")[0].split("|")[0].strip()
                return {
                    "name": name if name else "Technical Decision Maker",
                    "linkedin_url": url,
                    "headline": res.get("description", "")
                }
    return None

# 4. Main Pipeline Orchestrator
def generate_morning_pipeline():
    today_str = datetime.now().strftime("%Y-%m-%d")
    output_filename = f"daily_leads_{today_str}.csv"
    all_leads = []

    for bench in BENCH_PROFILES:
        print(f"\n=======================================================")
        print(f"Processing Bench: {bench['dev_id']} ({bench['tech_stack']})")
        print(f"=======================================================")
        
        companies = get_hiring_companies(bench["job_keyword"], max_companies=20)
        
        for item in companies[:20]:
            print(f"--> [Step 2] Finding Decision-Maker at: {item['company']}")
            dm = find_technical_decision_maker(item["company"], bench["target_titles"])
            
            lead_row = {
                "Date": today_str,
                "Bench_Stack": bench["tech_stack"],
                "Hiring_Company": item["company"],
                "Open_Requisition": item["job_title"],
                "Job_Link": item["job_url"],
                "Decision_Maker_Name": dm["name"] if dm else "Unknown",
                "Decision_Maker_URL": dm["linkedin_url"] if dm else "Manual Check Required",
                "Outreach_Hook": generate_option1_hook(
                    company=item["company"],
                    raw_title=item["job_title"],
                    bench_stack=bench["tech_stack"],
                    client_name="Daniel's engineering team at TLVTech"
                )
            }
            all_leads.append(lead_row)

    # 5. Export to CSV
    if all_leads:
        fieldnames = [
            "Date",
            "Bench_Stack",
            "Hiring_Company",
            "Open_Requisition",
            "Job_Link",
            "Decision_Maker_Name",
            "Decision_Maker_URL",
            "Outreach_Hook"
        ]
        with open(output_filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_leads)
        print(f"\n[✓] SUCCESS: Generated {len(all_leads)} qualified leads -> {output_filename}")
    else:
        print("\n[!] Warning: No leads collected. Check Apify token balance or search queries.")

if __name__ == "__main__":
    generate_morning_pipeline()
