#!/usr/bin/env python3
import os
import csv
import requests
import json
import datetime
import google.generativeai as genai
import sys
import time
import urllib.parse
import re
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Ensure directories exist
os.makedirs("preprocessed", exist_ok=True)
os.makedirs("processed", exist_ok=True)

print("Repository structure initialized. Starting GitHub repository indexing process...")

def get_github_token():
    """Get GitHub token from environment variable."""
    token = os.environ.get('GITHUB_PAT')
    
    if not token:
        print("Error: GitHub Personal Access Token not found.")
        print("Please set the GITHUB_PAT environment variable in your .env file.")
        sys.exit(1)
    
    return token

def fetch_github_repos(token):
    """Fetch all public repositories for a specific GitHub username."""
    headers = { 
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    all_repos = []
    page = 1
    per_page = 100  # Maximum allowed by GitHub API
    username = os.environ.get('GITHUB_USERNAME')
    
    if not username:
        print("Error: GitHub username not found.")
        print("Please set the GITHUB_USERNAME environment variable in your .env file.")
        sys.exit(1)
    
    print(f"Fetching repositories for GitHub user: {username}")
    
    while True:
        print(f"Fetching page {page} of repositories...")
        url = f'https://api.github.com/users/{username}/repos'
        response = requests.get(url, headers=headers, params={'per_page': per_page, 'page': page, 'type': 'public'})
        
        if response.status_code != 200:
            print(f"Error fetching repositories: {response.status_code}")
            print(response.text)
            sys.exit(1)
        
        repos = response.json()
        if not repos:
            break  # No more repositories to fetch
        
        all_repos.extend(repos)
        page += 1
        
        # Check if we've reached the last page
        if len(repos) < per_page:
            break
        
        # Respect GitHub's rate limits
        time.sleep(0.5)
        print(f"Found {len(repos)} repositories on page {page}")
    
    # Sort repositories by creation date (newest first)
    all_repos.sort(key=lambda x: x['created_at'], reverse=True)
    
    return all_repos

def save_repos_to_csv(repos):
    """Save repositories to a CSV file with timestamp in filename."""
    # Generate timestamp in DDMMYY_HHMM format
    timestamp = datetime.datetime.now().strftime("%d%m%y_%H%M")
    filename = f"preprocessed/github_repos_{timestamp}.csv"
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['name', 'url', 'created_at', 'description']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for repo in repos:
            writer.writerow({
                'name': repo['name'],
                'url': repo['html_url'],
                'created_at': repo['created_at'],
                'description': repo['description'] or ''
            })
    
    print(f"Saved {len(repos)} repositories to {filename}")
    return filename

def repair_json(json_str):
    """Attempt to repair malformed JSON."""
    print("Attempting to repair malformed JSON...")
    
    # Common JSON errors and fixes
    fixes = [
        # Fix missing commas between objects in arrays
        (r'}\s*\n\s*{', '}, {'),
        # Fix missing commas between array items
        (r'"\s*"', '", "'),
        # Fix trailing commas in arrays
        (r',\s*]', ']'),
        # Fix trailing commas in objects
        (r',\s*}', '}'),
        # Fix missing quotes around keys
        (r'([{,]\s*)([a-zA-Z0-9_]+)(\s*:)', r'\1"\2"\3'),
        # Fix unescaped quotes in strings (careful with this one)
        (r'([^\\])"([^"]*[^\\])"', r'\1\\"\2\\"'),
    ]
    
    repaired = json_str
    for pattern, replacement in fixes:
        repaired = re.sub(pattern, replacement, repaired)
    
    # Try to validate the repaired JSON
    try:
        json.loads(repaired)
        print("JSON successfully repaired!")
        return repaired
    except json.JSONDecodeError as e:
        print(f"Repair attempt failed: {e}")
        
        # If repair failed, try a more aggressive approach: extract all valid categories
        print("Trying to extract valid categories...")
        categories_pattern = r'{\s*"name":\s*"[^"]+",\s*"repositories":\s*\[(?:[^][]|\[[^][]*\])*\]\s*}'
        categories = re.findall(categories_pattern, json_str.replace('\n', ' '))
        if categories:
            return '{"categories": [' + ','.join(categories) + ']}'
        return None

def configure_genai():
    """Configure the Gemini API client."""
    # Get Gemini API key from environment variable
    api_key = os.environ.get('GEMINI_API_KEY')
    
    if not api_key:
        print("Error: Gemini API key not found.")
        print("Please set the GEMINI_API_KEY environment variable in your .env file.")
        sys.exit(1)
    
    genai.configure(api_key=api_key)
    
    # Get model name from environment variable or use default
    model_name = os.environ.get('GEMINI_MODEL', 'models/gemini-2.0-flash')
    print(f"Using model: {model_name}")
    
    return genai.GenerativeModel(model_name)
    
def categorize_repos_with_llm(csv_filename):
    """Use a language model to categorize repositories."""
    # Initialize Gemini model
    model = configure_genai()
    
    # Read CSV data
    with open(csv_filename, 'r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        repos = list(reader)
    
    # Prepare data for the language model
    repo_data = []
    for repo in repos:
        repo_data.append({
            'name': repo['name'],
            'url': repo['url'],
            'created_at': repo['created_at'],
            'description': repo['description']
        })
    
    # Create prompt for the language model
    prompt = f"""
    I have a list of GitHub repositories. Please categorize them into logical groups based on their names, descriptions, and other attributes.
    IMPORTANT: Your response must be valid JSON with no formatting errors. Do not include markdown code blocks or any text before or after the JSON.
    Each repository should belong to exactly one category. Create as many categories as needed to group repositories with significant commonalities.
    
    For each category, provide:
    1. A descriptive category name
    2. A list of repositories that belong to this category
    
    Here's the repository data:
    {json.dumps(repo_data, indent=2)}
    
    Format your response as a JSON object with this structure:
    {{
      "categories": [
        {{
          "name": "Category Name",
          "repositories": [
            {{ "name": "repo-name", "url": "repo-url" }}
          ]
        }}
      ]
    }}
    """
    
    print(f"Sending prompt to Gemini model to categorize {len(repos)} repositories...")
    # Call the language model
    try:
        print(f"Processing {len(repos)} repositories with Gemini...")
        response = model.generate_content(prompt)

        # Print a sample of the response for debugging
        print("\nRaw response from model (first 500 chars):")
        print("=" * 40)
        content_sample = response.text[:500] + "..." if len(response.text) > 500 else response.text
        print(content_sample)
        
        # Parse the response
        content = response.text
        # Extract JSON from the response (in case there's additional text)
        json_start = content.find('{')
        json_end = content.rfind('}') + 1
        print(f"Extracted JSON from position {json_start} to {json_end}")
        json_str = content[json_start:json_end]
        
        try:
            categorized_data = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON: {e}")
            print(f"JSON string (first 500 chars): {json_str[:500]}...")
            
            # Try to repair the JSON
            repaired_json = repair_json(json_str)
            if repaired_json:
                try:
                    categorized_data = json.loads(repaired_json)
                    print(f"Successfully categorized repositories into {len(categorized_data.get('categories', []))} categories")
                    print("Successfully parsed repaired JSON!")
                    return categorized_data
                except json.JSONDecodeError:
                    pass
            
            # If all repair attempts fail, create a minimal valid structure
            print("Creating minimal valid structure...")
            print("WARNING: Could not properly categorize repositories. Using fallback uncategorized structure.")
            return {"categories": [{"name": "Uncategorized", "repositories": []}]}
            
        return categorized_data
    except Exception as e:
        print(f"Error calling language model: {e}")
        # Return a minimal valid structure
        return {"categories": [{"name": "Uncategorized", "repositories": []}]}

def generate_markdown(categorized_data, csv_filename):
    """Generate a markdown file with categorized repositories."""
    # Use the same timestamp as the CSV file
    timestamp = os.path.basename(csv_filename).split('_', 1)[1].rsplit('.', 1)[0]
    md_filename = f"processed/github_repos_index_{timestamp}.md"
    
    print(f"Generating markdown file with {len(categorized_data.get('categories', []))} categories...")
    with open(md_filename, 'w', encoding='utf-8') as mdfile:
        mdfile.write("# GitHub Repositories Index\n\n")
        mdfile.write(f"Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        for category in categorized_data['categories']:
            mdfile.write(f"## {category['name']}\n\n")
            
            print(f"Adding {len(category.get('repositories', []))} repositories to category '{category['name']}'")
            for repo in category['repositories']:
                repo_name = repo['name']
                repo_url = repo['url']
                # Create a shields.io badge with a link
                # URL encode the repository name for the badge
                encoded_name = urllib.parse.quote_plus(repo_name)
                badge = f"[![{repo_name}](https://img.shields.io/badge/{encoded_name}-repository-blue)]({repo_url})"
                mdfile.write(f"{badge}\n\n")
    
    print(f"Generated markdown index at {md_filename}")
    return md_filename

def main():
    # Get GitHub token
    print("Starting GitHub repository indexing process...")
    token = get_github_token()
    
    # Fetch repositories
    print("Fetching GitHub repositories...")
    repos = fetch_github_repos(token)
    username = os.environ.get('GITHUB_USERNAME')
    print(f"Found {len(repos)} repositories for {username}")
    
    # Save to CSV
    csv_filename = save_repos_to_csv(repos)
    
    # Categorize repositories
    print("Categorizing repositories with language model...")
    categorized_data = categorize_repos_with_llm(csv_filename)
    
    # Generate markdown
    md_filename = generate_markdown(categorized_data, csv_filename)
    
    print("Done!")
    print(f"CSV file: {csv_filename}")
    print(f"Markdown index: {md_filename}")
    
    print("\nYou can view the generated markdown file with:")
    print(f"  cat {md_filename}")

if __name__ == "__main__":
    main()