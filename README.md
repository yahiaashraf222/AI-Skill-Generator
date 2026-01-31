# AI Skill Generator App

A Streamlit-based application that scrapes a website via its Sitemap XML and generates an AI Skill Bundle (Markdown files + Index) ready for use with AI agents.

## Features
- **Sitemap Parsing**: Automatically finds all pages from a sitemap.
- **Configurable Crawling**: Set crawl rate, thread count, and user agent.
- **Auto-Formatting**: Converts HTML pages to Markdown.
- **Skill Generation**: Creates a `SKILL.md` index and packages everything into a Zip file.

## Installation

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

1.  **Run the App**:
    ```bash
    streamlit run app.py
    ```

2.  **Open in Browser**:
    The app will open automatically (usually at `http://localhost:8501`).

3.  **Generate Skill**:
    - Enter the **Sitemap XML Link** (e.g., `https://example.com/sitemap.xml`).
    - Adjust **Crawl Rate** and **Threads** as needed.
    - Click **Start Generation**.
    - Download the `skill_bundle.zip` when complete.

## Output Structure

The generated zip file contains:
- `SKILL.md`: Main index file.
- `README.md`: Basic usage info.
- `references/`: Folder containing all scraped pages as Markdown files.
