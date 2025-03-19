# GitHub Repository Indexer with Gemini

A Python script that uses Google's Gemini AI to automatically categorize and organize your GitHub repositories into a structured markdown file.

## Overview

This tool fetches all public repositories for a specified GitHub user, categorizes them using the Gemini AI model, and generates a well-organized markdown index with repository links grouped by category.

## Features

- Fetches all public repositories for a GitHub user
- Uses Gemini AI to intelligently categorize repositories based on names and descriptions
- Generates a clean markdown file with repositories organized by category
- Creates clickable repository badges with links to each repository

## Requirements

- Python 3.6+
- GitHub Personal Access Token
- Google Gemini API Key
- Required Python packages (see requirements.txt)

## Setup

1. Clone this repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Create a `.env` file based on the provided `.env.example`:
   ```
   GITHUB_PAT=your_github_personal_access_token_here
   GITHUB_USERNAME=your_github_username_here
   GEMINI_API_KEY=your_gemini_api_key_here
   GEMINI_MODEL=models/gemini-2.0-flash
   ```

## Usage

Run the script:

```
python app.py
```

The script will:
1. Fetch your GitHub repositories
2. Save them to a CSV file in the `preprocessed` directory
3. Use Gemini to categorize the repositories
4. Generate a markdown index in the `processed` directory

## Output

The generated markdown file will organize your repositories by category, with each repository displayed as a clickable badge.
