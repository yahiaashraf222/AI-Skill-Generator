import streamlit as st
import os
import time
from scraper_engine import ScraperEngine, ScraperConfig
import shutil
import json
from urllib.parse import urlparse

# Set page configuration
st.set_page_config(
    page_title="AI Skill Generator",
    page_icon="🤖",
    layout="wide"
)

# --- CONFIG LOADING LOGIC (MUST BE AT TOP) ---
if 'pending_config_load' in st.session_state:
    config_data = st.session_state.pop('pending_config_load')
    st.session_state.skill_name_input = config_data.get('skill_name', '')
    st.session_state.skill_description_input = config_data.get('skill_description', '')
    st.session_state.skill_overview_input = config_data.get('skill_overview', '')
    st.session_state.crawl_mode_input = "Sitemap" if config_data.get('mode') == "sitemap" else "Recursive (Full Site)"
    st.session_state.sitemap_url_input = config_data.get('sitemap_url', '')
    st.session_state.base_url_input = config_data.get('base_url', '')
    st.session_state.max_pages_input = config_data.get('max_pages', 100)
    st.session_state.crawl_rate_input = config_data.get('crawl_rate', 0.5)
    st.session_state.threads_input = config_data.get('max_threads', 5)
    st.session_state.max_retries_input = config_data.get('max_retries', 3)
    st.session_state.user_agent_input = config_data.get('user_agent', '')
    st.toast("Configuration loaded! Switch to Generator tab to run.")
# ---------------------------------------------

def reset_environment():
    """Clean up generated files."""
    if os.path.exists("generated_skill"):
        shutil.rmtree("generated_skill")
    if os.path.exists("skill_bundle.zip"):
        os.remove("skill_bundle.zip")

def load_config_into_session(config_data):
    """Load configuration dictionary into session state."""
    st.session_state['pending_config_load'] = config_data
    st.rerun()

def get_url_tree(crawl_data):
    """Build a directory tree structure from crawl data URLs."""
    tree = {}
    for item in crawl_data:
        if item.get('status') != 'success':
            continue
            
        url = item.get('url', '')
        if not url:
            continue
            
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        if not path:
            continue
            
        parts = path.split('/')
        current = tree
        for part in parts:
            if part not in current:
                current[part] = {}
            current = current[part]
            
    return tree

def flatten_paths(tree, prefix=""):
    """Flatten the tree into a list of paths."""
    paths = []
    for key, value in tree.items():
        current_path = f"{prefix}/{key}" if prefix else key
        paths.append(current_path)
        paths.extend(flatten_paths(value, current_path))
    return paths

def create_sub_skill(original_dir, sub_path, new_skill_name):
    """Create a new skill from a subset of an existing crawl."""
    try:
        # Load original crawl data
        data_path = os.path.join(original_dir, "crawl_data.json")
        with open(data_path, 'r', encoding='utf-8') as f:
            crawl_data = json.load(f)
            
        # Filter items
        filtered_items = []
        for item in crawl_data:
            url = item.get('url', '')
            parsed = urlparse(url)
            path = parsed.path.strip('/')
            
            # Check if path starts with sub_path
            # Normalize slashes
            norm_path = path.replace('\\', '/')
            norm_sub = sub_path.strip('/').replace('\\', '/')
            
            if norm_path.startswith(norm_sub):
                filtered_items.append(item)
        
        if not filtered_items:
            return False, "No pages found matching this path."
            
        # Create new config
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        output_base = "generated_skills"
        skill_folder_name = new_skill_name.lower().replace(' ', '-')
        unique_folder_name = f"{skill_folder_name}-{timestamp}"
        output_dir = os.path.join(output_base, unique_folder_name)
        references_dir = os.path.join(output_dir, "references")
        
        os.makedirs(references_dir, exist_ok=True)
        
        # Copy files
        original_ref_dir = os.path.join(original_dir, "references")
        copied_count = 0
        
        for item in filtered_items:
            filename = item.get('filename')
            if filename:
                src = os.path.join(original_ref_dir, filename)
                dst = os.path.join(references_dir, filename)
                if os.path.exists(src):
                    shutil.copy2(src, dst)
                    copied_count += 1
                    
        # Generate new SKILL.md
        # We can reuse the engine logic or just write it here. Reusing is cleaner but needs config.
        # Let's simple-write it for now to avoid instantiating engine just for this.
        
        with open(os.path.join(output_dir, "SKILL.md"), 'w', encoding='utf-8') as f:
            f.write(f"---\nname: {new_skill_name}\ndescription: Extracted from {os.path.basename(original_dir)} (Path: {sub_path})\n---\n\n# Documentation\n\n## Overview\nSubset of documentation.\n\n## Reference File Index\n")
            for item in filtered_items:
                f.write(f"- [{item['title']}](references/{item['filename']})\n")

        with open(os.path.join(output_dir, "README.md"), 'w', encoding='utf-8') as f:
             f.write(f"# {new_skill_name}\n\nGenerated subset skill.")

        # Zip
        shutil.make_archive(os.path.join(output_dir, skill_folder_name), 'zip', output_dir)
        # Move zip inside? make_archive saves to base_name + .zip. 
        # If we want it inside, we target inside.
        zip_path = os.path.join(output_dir, f"{skill_folder_name}.zip")
        # shutil.make_archive does not easily put it inside the dir being zipped if it's recursive?
        # Let's use zipfile manually or careful paths.
        # Actually ScraperEngine puts zip INSIDE.
        import zipfile
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
             zipf.write(os.path.join(output_dir, "SKILL.md"), "SKILL.md")
             zipf.write(os.path.join(output_dir, "README.md"), "README.md")
             for root, dirs, files in os.walk(references_dir):
                 for file in files:
                     file_path = os.path.join(root, file)
                     arcname = os.path.join("references", file)
                     zipf.write(file_path, arcname)
                     
        return True, f"Created new skill '{new_skill_name}' with {copied_count} files."

    except Exception as e:
        return False, str(e)

def main():
    st.title("🤖 AI Skill Generator")
    st.markdown("Scrap a website and generate an AI Skill Zip file (Markdown format).")

    # Initialize Session State for Inputs if not present
    defaults = {
        'skill_name_input': "generated-skill",
        'skill_description_input': "AI Skill generated from website documentation.",
        'skill_overview_input': "This skill contains documentation scraped from the provided website.",
        'crawl_mode_input': "Sitemap",
        'sitemap_url_input': "",
        'base_url_input': "",
        'max_pages_input': 100,
        'crawl_rate_input': 0.5,
        'threads_input': 5,
        'max_retries_input': 3,
        'user_agent_input': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    # Sidebar Configuration
    st.sidebar.header("Configuration")
    
    # Mode Selection
    crawl_mode = st.sidebar.radio(
        "Crawl Mode",
        ("Sitemap", "Recursive (Full Site)"),
        key="crawl_mode_input",
        help="Choose 'Sitemap' to use an existing sitemap.xml, or 'Recursive' to discover links automatically."
    )
    
    sitemap_url = None
    base_url = None
    max_pages = 100
    
    if crawl_mode == "Sitemap":
        sitemap_url = st.sidebar.text_input(
            "Sitemap XML Link", 
            placeholder="https://example.com/sitemap.xml",
            key="sitemap_url_input",
            help="The URL to the website's sitemap.xml"
        )
    else:
        base_url = st.sidebar.text_input(
            "Base URL",
            placeholder="https://example.com/docs",
            key="base_url_input",
            help="The starting point for recursive crawling."
        )
        max_pages = st.sidebar.number_input(
            "Max Pages limit",
            min_value=1,
            max_value=100000,
            step=10,
            key="max_pages_input",
            help="Maximum number of pages to crawl to prevent infinite loops."
        )
    
    crawl_rate = st.sidebar.number_input(
        "Crawl Rate (seconds)", 
        min_value=0.1, 
        max_value=10.0, 
        step=0.1,
        key="crawl_rate_input",
        help="Delay between requests to avoid getting blocked."
    )
    
    threads = st.sidebar.slider(
        "Threads", 
        min_value=1, 
        max_value=20, 
        key="threads_input",
        help="Number of concurrent requests."
    )
    
    max_retries = st.sidebar.slider(
        "Max Retries",
        min_value=0,
        max_value=10,
        key="max_retries_input",
        help="Number of times to retry a failed request (e.g., on timeout)."
    )
    
    user_agent = st.sidebar.text_input(
        "User Agent", 
        key="user_agent_input",
        help="User Agent string to identify the scraper."
    )
    
    st.sidebar.markdown("---")
    st.sidebar.header("Skill Details")
    skill_name = st.sidebar.text_input("Skill Name", key="skill_name_input", help="Name of the skill in the YAML frontmatter.")
    skill_description = st.sidebar.text_input("Description", key="skill_description_input", help="Description of the skill.")
    skill_overview = st.sidebar.text_area("Overview", key="skill_overview_input", help="Detailed overview text in the skill documentation.")
    
    # Main Area
    tab1, tab2 = st.tabs(["Generator", "History"])

    with tab1:
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
                # Return not suitable here because we are in a tab, better use a flag or just stop
            elif crawl_mode == "Recursive (Full Site)" and not base_url:
                st.error("Please provide a Base URL.")
            else:
                # No longer resetting environment globally to preserve history
                # reset_environment() 
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
                    file_name=os.path.basename(st.session_state.zip_path),
                    mime="application/zip"
                )

    with tab2:
        st.header("📜 History")
        base_dir = "generated_skills"
        
        if not os.path.exists(base_dir):
            st.info("No history found.")
        else:
            # List directories sorted by creation time (newest first)
            dirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
            dirs.sort(key=lambda x: os.path.getctime(os.path.join(base_dir, x)), reverse=True)
            
            if not dirs:
                st.info("No generated skills found.")
            
            for d in dirs:
                dir_path = os.path.join(base_dir, d)
                # Try to find the zip file inside
                zip_files = [f for f in os.listdir(dir_path) if f.endswith('.zip')]
                zip_path = os.path.join(dir_path, zip_files[0]) if zip_files else None
                
                col1, col2, col3 = st.columns([3, 1, 1])
                
                with col1:
                    st.subheader(d)
                    creation_time = time.ctime(os.path.getctime(dir_path))
                    st.caption(f"Created: {creation_time}")
                    
                with col2:
                    if zip_path and os.path.exists(zip_path):
                        with open(zip_path, "rb") as fp:
                            st.download_button(
                                label="⬇️ Download",
                                data=fp,
                                file_name=f"{d}.zip",
                                mime="application/zip",
                                key=f"dl_{d}"
                            )
                    else:
                        st.warning("No Zip")
                        
                with col3:
                    if st.button("🗑️ Delete", key=f"del_{d}"):
                        try:
                            shutil.rmtree(dir_path)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error deleting: {e}")
                
                # Extended Actions for Update / Split
                with st.expander("⚙️ Advanced Options"):
                    # Load Config Action
                    config_path = os.path.join(dir_path, "config.json")
                    if os.path.exists(config_path):
                         if st.button("🔄 Load Settings to Generator", key=f"load_{d}"):
                             try:
                                 with open(config_path, 'r', encoding='utf-8') as f:
                                     config_data = json.load(f)
                                 load_config_into_session(config_data)
                             except Exception as e:
                                 st.error(f"Error loading config: {e}")
                    else:
                        st.caption("No configuration file found for this crawl.")
                        
                    # Split Action
                    data_path = os.path.join(dir_path, "crawl_data.json")
                    if os.path.exists(data_path):
                        st.markdown("#### ✂️ Split Skill by Path")
                        try:
                            with open(data_path, 'r', encoding='utf-8') as f:
                                crawl_data = json.load(f)
                            
                            tree = get_url_tree(crawl_data)
                            paths = flatten_paths(tree)
                            # Sort paths
                            paths.sort()
                            
                            # Filter paths that actually have content? 
                            # Flatten_paths returns all nodes.
                            
                            if not paths:
                                st.warning("No paths detected.")
                            else:
                                sub_path = st.selectbox("Select Path to Extract", [""] + paths, key=f"split_sel_{d}")
                                new_sub_name = st.text_input("New Skill Name", value=f"{d}-sub", key=f"split_name_{d}")
                                
                                if st.button("Extract Sub-Skill", key=f"btn_split_{d}"):
                                    if not sub_path:
                                        st.error("Please select a path.")
                                    else:
                                        success, msg = create_sub_skill(dir_path, sub_path, new_sub_name)
                                        if success:
                                            st.success(msg)
                                            time.sleep(2)
                                            st.rerun()
                                        else:
                                            st.error(msg)
                        except Exception as e:
                             st.error(f"Error reading crawl data: {e}")
                    else:
                        st.caption("No crawl data found for splitting.")

                st.divider()

if __name__ == "__main__":
    main()