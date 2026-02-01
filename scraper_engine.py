import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import markdownify
import os
import time
import zipfile
import re
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from urllib.parse import urlparse, urljoin
import logging
from dataclasses import dataclass
from typing import List, Callable, Optional, Set

import json
from dataclasses import dataclass, asdict

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ScraperConfig:
    mode: str = "sitemap" # 'sitemap' or 'recursive'
    sitemap_url: Optional[str] = None
    base_url: Optional[str] = None
    crawl_rate: float = 0.5
    max_threads: int = 5
    user_agent: str = "Mozilla/5.0"
    max_pages: int = 100 # Safety limit for recursive mode
    max_retries: int = 3 # New: Max retries for requests
    skill_name: str = "generated-skill"
    skill_description: str = "AI Skill generated from website documentation."
    skill_overview: str = "This skill contains documentation scraped from the provided website."

class ScraperEngine:
    def __init__(self, config: ScraperConfig, progress_callback: Optional[Callable[[str, float], None]] = None):
        self.config = config
        self.progress_callback = progress_callback
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': self.config.user_agent})
        
        # Configure Retries
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=1, # Wait 1s, 2s, 4s...
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        
        # Determine output directory based on skill name
        self.skill_folder_name = self._slugify(self.config.skill_name)
        # Use a timestamp if name is default or empty to ensure some uniqueness/history tracking? 
        # User asked for "auto separate by site name", so skill name is the best proxy.
        # To avoid overwriting same skill name if run multiple times, maybe we should NOT append timestamp unless requested.
        # But for "history", separate folders are better. 
        # Let's append a short timestamp to guarantee uniqueness for history tracking.
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        self.output_base = "generated_skills"
        self.unique_folder_name = f"{self.skill_folder_name}-{timestamp}"
        self.output_dir = os.path.join(self.output_base, self.unique_folder_name)
        self.references_dir = os.path.join(self.output_dir, "references")
        
        self._ensure_directories()
        
        # Setup File Logging
        self.log_file = os.path.join(self.output_dir, "crawl.log")
        self.file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        self.file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(self.file_handler)
        
    def _cleanup_logging(self):
        """Close and remove the file handler."""
        if hasattr(self, 'file_handler'):
            self.file_handler.close()
            logger.removeHandler(self.file_handler)

    def _ensure_directories(self):
        if not os.path.exists(self.references_dir):
            os.makedirs(self.references_dir)

    def save_metadata(self, results: List[dict]):
        """Save configuration and crawl results for future reference."""
        # Save Config
        config_path = os.path.join(self.output_dir, "config.json")
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(self.config), f, indent=4)
            
        # Save Crawl Data
        data_path = os.path.join(self.output_dir, "crawl_data.json")
        with open(data_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=4)

    def _slugify(self, text: str) -> str:
        """Convert text to a valid filename."""
        if not text:
            return "untitled"
        text = text.lower()
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[-\s]+', '-', text).strip('-')
        return text or "untitled"

    def _is_internal_url(self, url: str, base_domain: str) -> bool:
        """Check if URL belongs to the same domain."""
        try:
            parsed = urlparse(url)
            return parsed.netloc == base_domain or parsed.netloc == ""
        except:
            return False

    def fetch_sitemap_urls(self) -> List[str]:
        """Fetch and parse the sitemap to get all URLs."""
        try:
            if self.progress_callback:
                self.progress_callback("Fetching sitemap...", 0.0)
            
            response = self.session.get(self.config.sitemap_url, timeout=30) # Increased timeout
            response.raise_for_status()
            
            # Try parsing as XML first
            try:
                soup = BeautifulSoup(response.content, 'xml')
                urls = [loc.text.strip() for loc in soup.find_all('loc')]
            except:
                # Fallback to standard parser if XML fails (some sitemaps are plain text or weird HTML)
                soup = BeautifulSoup(response.content, 'html.parser')
                urls = [loc.text.strip() for loc in soup.find_all('loc')]
                
            if not urls:
                # Maybe it's a text file?
                urls = [line.strip() for line in response.text.split('\n') if line.strip().startswith('http')]

            logger.info(f"Found {len(urls)} URLs in sitemap.")
            return urls
        except Exception as e:
            logger.error(f"Error fetching sitemap: {e}")
            raise

    def process_url(self, url: str) -> dict:
        """Fetch a single URL, convert to markdown, and save."""
        try:
            # Respect crawl rate
            time.sleep(self.config.crawl_rate)
            
            # Timeout increased to 30s to reduce read timeouts on slow servers
            response = self.session.get(url, timeout=30) 
            response.raise_for_status()
            
            # Pre-parsing to extract links BEFORE cleanup
            soup = BeautifulSoup(response.content, 'html.parser')
            
            extracted_links = []
            if self.config.mode == "recursive":
                base_domain = urlparse(self.config.base_url).netloc
                for a_tag in soup.find_all('a', href=True):
                    href = a_tag['href']
                    full_url = urljoin(url, href)
                    # Remove fragment
                    full_url = full_url.split('#')[0]
                    
                    if self._is_internal_url(full_url, base_domain):
                        # Filter out obviously non-page resources
                        if not any(full_url.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.pdf', '.zip', '.css', '.js']):
                            if full_url.startswith("http"): # Ensure it's http/https
                                extracted_links.append(full_url)

            # Cleanup for Content
            for tag in soup(['script', 'style', 'nav', 'footer', 'iframe', 'header', 'aside']):
                tag.decompose()
                
            title = soup.title.string if soup.title else "No Title"
            title = title.strip() if title else "Untitled"
            
            # Convert to markdown
            md_content = markdownify.markdownify(str(soup), heading_style="ATX")
            
            # Add Title at the top
            full_content = f"# {title}\n\n{md_content}"
            
            # Generate filename
            filename = self._slugify(title) + ".md"
            if len(filename) > 100: # Truncate if too long
                filename = filename[:100] + ".md"
            
            # Avoid filename collisions in a simple way (not perfect but helpful)
            # In a real app, we'd check if file exists and increment, but for now overwriting or unique-by-title is acceptable constraint
            
            filepath = os.path.join(self.references_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(full_content)
                
            return {
                "url": url,
                "title": title,
                "filename": filename,
                "status": "success",
                "extracted_links": extracted_links
            }
            
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            return {
                "url": url,
                "title": "Error",
                "filename": "",
                "status": "failed",
                "error": str(e),
                "extracted_links": []
            }

    def generate_skill_md(self, scraped_data: List[dict]):
        """Generate the SKILL.md file."""
        skill_content = f"""---
name: {self.config.skill_name}
description: {self.config.skill_description}
---

# Documentation

## Overview
{self.config.skill_overview}

## Reference File Index

| File | Content |
|---|---|
"""
        # Deduplicate entries by filename in case of multiple URLs mapping to same title
        seen_filenames = set()
        for item in scraped_data:
            if item['status'] == 'success' and item['filename'] not in seen_filenames:
                skill_content += f"| `{item['filename']}` | {item['title']} |\n"
                seen_filenames.add(item['filename'])
        
        with open(os.path.join(self.output_dir, "SKILL.md"), 'w', encoding='utf-8') as f:
            f.write(skill_content)

    def generate_readme(self):
        """Generate a basic README.md."""
        readme_content = """# Generated AI Skill

This skill was generated by the AI Skill Generator App.

## Usage
Install this skill into your AI agent or editor.
"""
        with open(os.path.join(self.output_dir, "README.md"), 'w', encoding='utf-8') as f:
            f.write(readme_content)

    def create_zip(self) -> str:
        """Zip the generated content and return the path to the zip file."""
        # Zip file inside the skill folder
        zip_filename = f"{self.skill_folder_name}.zip"
        zip_path = os.path.join(self.output_dir, zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add SKILL.md and README.md
            if os.path.exists(os.path.join(self.output_dir, "SKILL.md")):
                zipf.write(os.path.join(self.output_dir, "SKILL.md"), "SKILL.md")
            if os.path.exists(os.path.join(self.output_dir, "README.md")):
                zipf.write(os.path.join(self.output_dir, "README.md"), "README.md")
            
            # Add reference files
            for root, dirs, files in os.walk(self.references_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.join("references", file)
                    zipf.write(file_path, arcname)
                    
        return zip_path

    def run(self):
        """Main execution method."""
        # self._ensure_directories() # Already called in __init__
        
        results = []
        visited_urls = set()
        pending_urls = set()

        try:
            # Initial Population
            if self.config.mode == "sitemap":
                initial_urls = self.fetch_sitemap_urls()
                for url in initial_urls:
                    pending_urls.add(url)
            elif self.config.mode == "recursive":
                if not self.config.base_url:
                    raise ValueError("Base URL is required for recursive mode.")
                pending_urls.add(self.config.base_url)
            
            total_urls_estimate = len(pending_urls) if self.config.mode == "sitemap" else "Unknown"
            completed_count = 0
            last_update_time = 0
            
            with ThreadPoolExecutor(max_workers=self.config.max_threads) as executor:
                # Map future to URL
                future_to_url = {}
                
                # Submit initial batch
                while pending_urls and (self.config.mode == "sitemap" or completed_count + len(future_to_url) < self.config.max_pages):
                    # If sitemap, submit all. If recursive, limit by max_pages.
                    
                    # Careful not to submit too many at once if recursive to allow discovery?
                    # Actually, standard pool usage is fine.
                    
                    # We need to drain pending_urls and move them to visited/future
                    
                    # Take a snapshot of pending to iterate safely
                    to_submit = list(pending_urls)
                    pending_urls.clear() # Clear pending as we are submitting them
                    
                    for url in to_submit:
                        if url not in visited_urls:
                            visited_urls.add(url)
                            future = executor.submit(self.process_url, url)
                            future_to_url[future] = url

                # Process Loop
                while future_to_url:
                    # Wait for at least one future to complete
                    done, not_done = wait(future_to_url.keys(), return_when=FIRST_COMPLETED)
                    
                    for future in done:
                        url = future_to_url.pop(future)
                        try:
                            data = future.result()
                            results.append(data)
                            completed_count += 1
                            
                            # Update Progress (Throttled to max 10 updates per second)
                            current_time = time.time()
                            if self.progress_callback and (current_time - last_update_time > 0.1):
                                last_update_time = current_time
                                if isinstance(total_urls_estimate, int) and total_urls_estimate > 0:
                                    progress = min(1.0, completed_count / total_urls_estimate)
                                    self.progress_callback(f"Processed {completed_count}/{total_urls_estimate} (Pending: {len(pending_urls)})", progress)
                                else:
                                    self.progress_callback(f"Processed {completed_count} (Pending: {len(pending_urls)})", 0.5)

                            # Handle Recursive Discovery
                            if self.config.mode == "recursive" and data['status'] == 'success':
                                new_links = data.get('extracted_links', [])
                                for link in new_links:
                                    if link not in visited_urls:
                                        pending_urls.add(link)
                                        
                        except Exception as exc:
                            logger.error(f"{url} generated an exception: {exc}")
                        
                    # Refill Queue if recursive
                    if self.config.mode == "recursive":
                         while pending_urls and completed_count + len(future_to_url) < self.config.max_pages:
                             # Pull from pending
                             # To avoid submitting all at once again, let's take chunks or just loop
                             # Since we are inside the loop, just take what we can
                             
                             # NOTE: pending_urls is a set, so popping might be random.
                             # Let's convert to list to slice if needed, or just iterate
                             to_add = []
                             while pending_urls and len(future_to_url) + len(to_add) < self.config.max_threads * 2: # Keep buffer full
                                 to_add.append(pending_urls.pop())
                             
                             for url in to_add:
                                if url not in visited_urls:
                                    visited_urls.add(url)
                                    future = executor.submit(self.process_url, url)
                                    future_to_url[future] = url
                             
                             if not to_add:
                                 break

            # Generate Output Files
            self.generate_skill_md(results)
            self.generate_readme()
            self.save_metadata(results)
            zip_path = self.create_zip()
            
            return zip_path, results

        except Exception as e:
            logger.error(f"Fatal error in run: {e}")
            raise
        finally:
            self._cleanup_logging()

if __name__ == "__main__":
    pass
