from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager
import csv
import time
from colorama import Fore, Back, Style, init
import argparse
from datetime import datetime, timezone

# Initialize colorama
init(autoreset=True)

def debug_print(message, color=Fore.BLUE):
    print(f"{color}{message}{Style.RESET_ALL}")

def setup_driver():
    debug_print("Setting up the Chrome driver...", Fore.CYAN)
    chrome_options = Options()
    # Remove the headless option
    # chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        debug_print("Chrome driver set up successfully.", Fore.GREEN)
        return driver
    except Exception as e:
        debug_print(f"Error setting up Chrome driver: {str(e)}", Fore.RED)
        raise

def wait_for_element(driver, by, value, timeout=30):
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
        debug_print(f"Element found: {value}", Fore.GREEN)
        return element
    except TimeoutException:
        debug_print(f"Timeout waiting for element: {value}", Fore.RED)
        return None

def safe_find_element(driver, by, value):
    try:
        return WebDriverWait(driver, 10).until(EC.presence_of_element_located((by, value)))
    except (NoSuchElementException, StaleElementReferenceException):
        return None

def filter_us_jobs(driver):
    debug_print("Filtering for US jobs...", Fore.YELLOW)
    try:
        # Click on the Location filter
        location_filter = wait_for_element(driver, By.CSS_SELECTOR, "button[data-automation-id='distanceLocation']")
        if not location_filter:
            debug_print("Location filter not found. Page might not have loaded correctly.", Fore.RED)
            return False
        driver.execute_script("arguments[0].click();", location_filter)

        # Wait for the filter menu to appear
        filter_menu = wait_for_element(driver, By.CSS_SELECTOR, "div[data-automation-id='filterMenu']")
        if not filter_menu:
            debug_print("Filter menu not found. Filter options might not have loaded.", Fore.RED)
            return False

        # Find the Locations section
        locations_section = wait_for_element(filter_menu, By.XPATH, ".//fieldset[.//span[text()='Locations']]")
        if not locations_section:
            debug_print("Locations section not found in the filter menu.", Fore.RED)
            return False

        # Find the United States checkbox
        us_checkbox = wait_for_element(locations_section, By.XPATH, ".//input[@id='2fcb99c455831013ea52fb338f2932d8']")
        if not us_checkbox:
            debug_print("United States checkbox not found.", Fore.RED)
            return False

        # Check if the US checkbox is already selected
        if not us_checkbox.is_selected():
            driver.execute_script("arguments[0].click();", us_checkbox)

        # Find and click the View Jobs button
        view_jobs_button = wait_for_element(driver, By.CSS_SELECTOR, "button[data-automation-id='viewAllJobsButton']")
        if not view_jobs_button:
            debug_print("View Jobs button not found.", Fore.RED)
            return False
        driver.execute_script("arguments[0].click();", view_jobs_button)

        # Wait for the page to update
        time.sleep(3)
        debug_print("US jobs filter applied successfully.", Fore.GREEN)
        return True
    except Exception as e:
        debug_print(f"Error applying US jobs filter: {str(e)}", Fore.RED)
        return False

def scrape_workday_jobs(url, max_pages=None, max_retries=3):
    driver = None
    for attempt in range(max_retries):
        try:
            driver = setup_driver()
            debug_print(f"Navigating to URL: {url}", Fore.YELLOW)
            driver.get(url)

            if not filter_us_jobs(driver):
                debug_print("Failed to apply US jobs filter. Retrying...", Fore.YELLOW)
                continue
            
            job_count_element = wait_for_element(driver, By.CSS_SELECTOR, "[data-automation-id='jobFoundText']", timeout=30)
            if not job_count_element:
                debug_print("Job count not found. Page might not have loaded correctly. Retrying...", Fore.YELLOW)
                continue
            
            job_count = int(job_count_element.text.split()[0])
            total_pages = (job_count - 1) // 20 + 1  # Assuming 20 jobs per page
            debug_print(f"Total jobs: {job_count}, Total pages to scrape: {total_pages}", Fore.MAGENTA)
            
            jobs = []
            processed_job_ids = set()
            scrape_timestamp = datetime.now(timezone.utc).isoformat()
            
            for page in range(1, total_pages + 1):
                debug_print(f"Scraping page {page} of {total_pages}...", Fore.MAGENTA)
                
                # Wait for job listings to load
                WebDriverWait(driver, 3).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li.css-1q2dra3"))
                )
                
                # Use JavaScript to get all job elements
                job_elements = driver.execute_script("""
                    return Array.from(document.querySelectorAll('li.css-1q2dra3')).map(el => ({
                        title: el.querySelector('a[data-automation-id="jobTitle"]')?.textContent,
                        url: el.querySelector('a[data-automation-id="jobTitle"]')?.href,
                        location: el.querySelector('dd.css-129m7dg')?.textContent,
                        job_id: el.querySelector('li.css-h2nt8k')?.textContent,
                        scrape_timestamp: '""" + scrape_timestamp + """'
                    }));
                """)
                
                debug_print(f"Found {len(job_elements)} job listings on page {page}.", Fore.GREEN)
                
                new_jobs_on_page = 0
                for job in job_elements:
                    if job['job_id'] not in processed_job_ids:
                        jobs.append(job)
                        processed_job_ids.add(job['job_id'])
                        new_jobs_on_page += 1
                
                debug_print(f"Added {new_jobs_on_page} new jobs from page {page}", Fore.CYAN)
                
                if new_jobs_on_page == 0 and page > 1:
                    debug_print("No new jobs on this page. Ending scrape.", Fore.YELLOW)
                    break
                
                if max_pages and page >= max_pages:
                    debug_print(f"Reached specified maximum of {max_pages} pages. Ending scrape.", Fore.YELLOW)
                    break
                
                if page < total_pages:
                    try:
                        debug_print(f"Attempting to navigate to page {page + 1}...", Fore.YELLOW)
                        
                        # Scroll to the bottom of the page
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(2)  # Wait for any lazy-loaded elements
                        debug_print("Scrolled to bottom of page", Fore.CYAN)

                        # Retry mechanism for finding and clicking the next button
                        max_retries = 3
                        for retry in range(max_retries):
                            try:
                                debug_print(f"Attempt {retry + 1} to find and click 'next' button", Fore.YELLOW)
                                
                                # Wait for the next button with a longer timeout
                                next_button = WebDriverWait(driver, 20).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button[aria-label='next']"))
                                )
                                debug_print("'Next' button found", Fore.GREEN)
                                
                                driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                                time.sleep(1)  # Wait for the button to be fully in view
                                
                                # Try to click using JavaScript
                                driver.execute_script("arguments[0].click();", next_button)
                                debug_print("Clicked 'next' button", Fore.GREEN)

                                time.sleep(3)  # Wait for the page to load
                                
                                # Check if new jobs are loaded
                                new_job_elements = driver.execute_script("""
                                    return Array.from(document.querySelectorAll('li.css-1q2dra3')).map(el => ({
                                        title: el.querySelector('a[data-automation-id="jobTitle"]')?.textContent,
                                        url: el.querySelector('a[data-automation-id="jobTitle"]')?.href,
                                        location: el.querySelector('dd.css-129m7dg')?.textContent,
                                        job_id: el.querySelector('li.css-h2nt8k')?.textContent
                                    }));
                                """)
                                
                                if len(new_job_elements) > 0:
                                    debug_print(f"Successfully navigated to page {page + 1}", Fore.GREEN)
                                    break
                                else:
                                    debug_print("No new jobs loaded, retrying...", Fore.YELLOW)
                            except Exception as e:
                                debug_print(f"Error during pagination attempt {retry + 1}: {str(e)}", Fore.RED)
                                if retry == max_retries - 1:
                                    raise  # Re-raise the exception if all retries failed
                                time.sleep(2)  # Wait before retrying
                        
                    except TimeoutException:
                        debug_print("Timeout: Couldn't find next button or it's not clickable. Ending scrape.", Fore.YELLOW)
                        break
                    except Exception as e:
                        debug_print(f"Unhandled error during pagination: {str(e)}", Fore.RED)
                        break
            
            return jobs
        
        except WebDriverException as e:
            debug_print(f"WebDriver error: {str(e)}", Fore.RED)
        except Exception as e:
            debug_print(f"An unexpected error occurred: {str(e)}", Fore.RED)
        finally:
            if driver:
                debug_print("Closing the browser...", Fore.CYAN)
                driver.quit()
        
        if attempt < max_retries - 1:
            debug_print(f"Retrying... Attempt {attempt + 2} of {max_retries}", Fore.YELLOW)
        else:
            debug_print("Max retries reached. Scraping failed.", Fore.RED)
    
    return jobs

def save_to_csv(jobs, filename='nvidia_us_jobs.csv'):
    debug_print(f"Saving {len(jobs)} jobs to {filename}...", Fore.YELLOW)
    with open(filename, 'w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=['title', 'location', 'job_id', 'url', 'scrape_timestamp'])
        writer.writeheader()
        for job in jobs:
            writer.writerow(job)
    debug_print(f"Jobs saved successfully to {filename}", Fore.GREEN)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape job listings from NVIDIA's Workday site.")
    parser.add_argument("-p", "--pages", type=int, help="Maximum number of pages to scrape")
    args = parser.parse_args()

    url = "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
    debug_print("Starting the job scraping process...", Fore.CYAN)
    jobs = scrape_workday_jobs(url, max_pages=args.pages)
    
    if jobs:
        debug_print(f"Found {len(jobs)} job listings.", Fore.GREEN)
        save_to_csv(jobs)
    else:
        debug_print("No job listings found.", Fore.RED)
    
    debug_print("Script execution completed.", Fore.CYAN)