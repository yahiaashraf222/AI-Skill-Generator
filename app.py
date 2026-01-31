import streamlit as st
import os
import time
from scraper_engine import ScraperEngine, ScraperConfig
import shutil

# Set page configuration
st.set_page_config(
    page_title="AI Skill Generator",
    page_icon="🤖",
    layout="wide"
)

def reset_environment():
    """Clean up generated files."""
    if os.path.exists("generated_skill"):
        shutil.rmtree("generated_skill")
    if os.path.exists("skill_bundle.zip"):
        os.remove("skill_bundle.zip")

def main():
    st.title("🤖 AI Skill Generator")
    st.markdown("Scrap a website and generate an AI Skill Zip file (Markdown format).")

    # Sidebar Configuration
    st.sidebar.header("Configuration")
    
    # Mode Selection
    crawl_mode = st.sidebar.radio(
        "Crawl Mode",
        ("Sitemap", "Recursive (Full Site)"),
        help="Choose 'Sitemap' to use an existing sitemap.xml, or 'Recursive' to discover links automatically."
    )
    
    sitemap_url = None
    base_url = None
    max_pages = 100
    
    if crawl_mode == "Sitemap":
        sitemap_url = st.sidebar.text_input(
            "Sitemap XML Link", 
            placeholder="https://example.com/sitemap.xml",
            help="The URL to the website's sitemap.xml"
        )
    else:
        base_url = st.sidebar.text_input(
            "Base URL",
            placeholder="https://example.com/docs",
            help="The starting point for recursive crawling."
        )
        max_pages = st.sidebar.number_input(
            "Max Pages limit",
            min_value=1,
            max_value=100000,
            value=100,
            step=10,
            help="Maximum number of pages to crawl to prevent infinite loops."
        )
    
    crawl_rate = st.sidebar.number_input(
        "Crawl Rate (seconds)", 
        min_value=0.1, 
        max_value=10.0, 
        value=0.5, 
        step=0.1,
        help="Delay between requests to avoid getting blocked."
    )
    
    threads = st.sidebar.slider(
        "Threads", 
        min_value=1, 
        max_value=20, 
        value=5,
        help="Number of concurrent requests."
    )
    
    max_retries = st.sidebar.slider(
        "Max Retries",
        min_value=0,
        max_value=10,
        value=3,
        help="Number of times to retry a failed request (e.g., on timeout)."
    )
    
    user_agent = st.sidebar.text_input(
        "User Agent", 
        value="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        help="User Agent string to identify the scraper."
    )
    
    st.sidebar.markdown("---")
    st.sidebar.header("Skill Details")
    skill_name = st.sidebar.text_input("Skill Name", value="generated-skill", help="Name of the skill in the YAML frontmatter.")
    skill_description = st.sidebar.text_input("Description", value="AI Skill generated from website documentation.", help="Description of the skill.")
    skill_overview = st.sidebar.text_area("Overview", value="This skill contains documentation scraped from the provided website.", help="Detailed overview text in the skill documentation.")

    # Main Area
    if "zip_path" not in st.session_state:
        st.session_state.zip_path = None
    if "logs" not in st.session_state:
        st.session_state.logs = []

    start_button = st.button("🚀 Start Generation", type="primary")
    
    status_container = st.container()
    progress_bar = status_container.progress(0)
    status_text = status_container.empty()
    log_area = st.empty()

    if start_button:
        # Validation
        if crawl_mode == "Sitemap" and not sitemap_url:
            st.error("Please provide a Sitemap XML Link.")
            return
        if crawl_mode == "Recursive (Full Site)" and not base_url:
            st.error("Please provide a Base URL.")
            return

        # Reset previous run
        reset_environment()
        st.session_state.logs = []
        st.session_state.zip_path = None
        
        mode_str = "sitemap" if crawl_mode == "Sitemap" else "recursive"
        
        config = ScraperConfig(
            mode=mode_str,
            sitemap_url=sitemap_url,
            base_url=base_url,
            crawl_rate=crawl_rate,
            max_threads=threads,
            user_agent=user_agent,
            max_pages=max_pages,
            max_retries=max_retries,
            skill_name=skill_name,
            skill_description=skill_description,
            skill_overview=skill_overview
        )
        
        def update_progress(msg, progress):
            progress_bar.progress(progress)
            status_text.text(msg)
            
        try:
            engine = ScraperEngine(config, progress_callback=update_progress)
            
            with st.spinner(f"Scraping in {crawl_mode} mode..."):
                zip_path, results = engine.run()
                
            st.session_state.zip_path = zip_path
            
            success_count = sum(1 for r in results if r['status'] == 'success')
            failed_count = len(results) - success_count
            
            st.success(f"Completed! Scraped {success_count} pages. ({failed_count} failed)")
            
            # Show simple stats
            with st.expander("See Details"):
                for res in results:
                    if res['status'] == 'success':
                        st.write(f"✅ {res['title']} -> {res['filename']}")
                    else:
                        st.error(f"❌ {res['url']} - {res.get('error')}")

        except Exception as e:
            st.error(f"An error occurred: {str(e)}")

    # Download Button
    if st.session_state.zip_path and os.path.exists(st.session_state.zip_path):
        with open(st.session_state.zip_path, "rb") as fp:
            st.download_button(
                label="📦 Download Skill Zip",
                data=fp,
                file_name="skill_bundle.zip",
                mime="application/zip"
            )

if __name__ == "__main__":
    main()
