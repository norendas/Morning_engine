import os
import requests
import json
import csv
from datetime import datetime

# Configure your Apify API Token
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")
HEADERS = {"Content-Type": "application/json"}

# 1. Define the Bench Profile (Targeting 20 prospects per engineer)
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

def run_apify_actor(actor_id, run_input):
    """Triggers an Apify actor and waits for dataset results."""
    run_url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items?token={APIFY_TOKEN}"
    response = requests.post(run_url, headers=HEADERS, json=run_input, timeout=180)
    if response.status_code in [200, 201]:
        return response.json()
    else:
        print(f"Error calling {actor_id}: {response.text}")
        return []

def get_hiring_companies(keyword, max_companies=20):
    """Pulls companies posting relevant developer roles in the US/UK."""
    print(f"--> [Step 1] Scraping live job signals for: {keyword}...")
    run_input = {
        "keywords": keyword,
        "location": "United States",
        "datePosted": "past-week",
        "maxItems": max_companies
    }
    # Uses Apify's public LinkedIn Jobs Scraper
    jobs = run_apify_actor("logical_scrapers~linkedin-jobs-scraper", run_input)
    
    unique_companies = []
    seen = set()
    for job in jobs:
        c_name = job.get("company")
        if c_name and c_name not in seen:
            seen.add(c_name)
            unique_companies.append({
                "company": c_name,
                "job_title": job.get("title"),
                "job_url": job.get("jobUrl") or job.get("sourceUrl")
            })
    return unique_companies

def find_technical_decision_maker(company_name, target_titles_query):
    """Uses Apify Google Search Scraper to execute X-Ray lookup for CTO / VP Eng."""
    search_query = f'site:linkedin.com/in "{company_name}" {target_titles_query} -jobs'
    run_input = {
        "queries": search_query,
        "maxPagesPerQuery": 1,
        "resultsPerPage": 3
    }
    # Uses Apify's official Google Search Scraper
    search_results = run_apify_actor("apify~google-search-scraper", run_input)
    
    if search_results and "organicResults" in search_results[0]:
        for res in search_results[0]["organicResults"]:
            url = res.get("url", "")
            if "linkedin.com/in/" in url:
                title_line = res.get("title", "")
                name = title_line.split("-")[0].strip() if "-" in title_line else title_line.split("|")[0].strip()
                return {
                    "name": name,
                    "linkedin_url": url,
                    "headline": res.get("description", "")
                }
    return None

def generate_morning_pipeline():
    today_str = datetime.now().strftime("%Y-%m-%d")
    output_filename = f"daily_leads_{today_str}.csv"
    
    all_leads = []

    for bench in BENCH_PROFILES:
        print(f"\nProcessing Bench: {bench['dev_id']} ({bench['tech_stack']})")
        hiring_companies = get_hiring_companies(bench["job_keyword"], max_companies=20)
        
        count = 0
        for item in hiring_companies:
            if count >= 20:
                break
            
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
                "Outreach_Hook": f"Saw {item['company']} is recruiting for a {item['job_title']}. We have senior {bench['tech_stack']} pods ready to deploy immediately."
            }
            all_leads.append(lead_row)
            count += 1

    # Write output to CSV
    keys = all_leads[0].keys() if all_leads else []
    if keys:
        with open(output_filename, "w", newline="", encoding="utf-8") as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(all_leads)
        print(f"\n SUCCESS: Sourced {len(all_leads)} prospects. Saved to {output_filename}")

if __name__ == "__main__":
    generate_morning_pipeline()