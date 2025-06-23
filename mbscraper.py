import time
import os
import re
import json
from urllib.parse import urlparse
from seleniumbase import Driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Configuration
max_articles = 500
base_url = "https://mb.com.ph/category/business?page="
output_dir = r"D:\python\kudalari\labalabajantan\labalabajantan\tools\SeleniumBase"
articles_dir = os.path.join(output_dir, "Articles")
images_dir = os.path.join(output_dir, "Images")
os.makedirs(articles_dir, exist_ok=True)
os.makedirs(images_dir, exist_ok=True)

def sanitize_filename(text):
    return re.sub(r'[\\/*?:"<>|]', "_", text)[:100].strip()

def slug_from_url(url):
    return urlparse(url).path.rstrip("/").split("/")[-1]

def scroll_to_bottom(driver, pause=1.0, max_scrolls=30):
    last_height = driver.execute_script("return document.body.scrollHeight")
    for _ in range(max_scrolls):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
    print("🔽 Scrolling finished")

def is_cloudflare_challenge(driver):
    try:
        title = driver.title.lower()
        if "just a moment" in title or "checking your browser" in title:
            print("☁️ Cloudflare challenge detected via title")
            return True
    except:
        pass
    return False

# Start timer
start_time = time.time()

# ✅ Initialize driver & bypass Cloudflare
driver = Driver(uc=True, headless=False)
driver.uc_open_with_reconnect(f"{base_url}1", 4)
driver.uc_gui_click_captcha()
WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.sw-grid-a")))
print("✅ First page loaded and CAPTCHA bypassed")
scroll_to_bottom(driver)

# 🔍 Collect article links
all_links = []
page = 1
while len(all_links) < max_articles:
    if page != 1:
        driver.get(f"{base_url}{page}")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.sw-grid-a")))
        scroll_to_bottom(driver)
    link_elements = driver.find_elements("css selector", ".d-flex a.mb-black")
    page_links = [el.get_attribute("href") for el in link_elements if el.get_attribute("href")]
    if not page_links:
        break
    all_links.extend(page_links)
    all_links = list(dict.fromkeys(all_links))
    print(f"📄 Page {page}: {len(page_links)} links, total: {len(all_links)}")
    page += 1

all_links = all_links[:max_articles]
with open("link.json", "w", encoding="utf-8") as f:
    json.dump(all_links, f, indent=2)
print("💾 All links saved to link.json")

# 🚀 Process each article
for idx, link in enumerate(all_links, start=1):
    try:
        slug = slug_from_url(link)
        driver.execute_script(f"window.open('{link}', '_blank');")
        driver.switch_to.window(driver.window_handles[-1])
        time.sleep(3)

        if is_cloudflare_challenge(driver):
            driver.uc_gui_click_captcha()
            WebDriverWait(driver, 15).until(lambda d: not is_cloudflare_challenge(d))
            print("✅ Cloudflare bypassed for article")

        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#widget_1559 h1")))
            title = driver.find_element("css selector", "#widget_1559 h1").text.strip()
            content = driver.find_element("css selector", "div.article-full-body").text.strip()

            # 💾 Save article (initially without images)
            json_path = os.path.join(articles_dir, f"{slug}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump({
                    "title": title,
                    "content": content,
                    "images": [],
                    "source_url": link
                }, f, indent=2, ensure_ascii=False)
            print(f"✅ Article saved to: {json_path}")

            # 🖼️ Extract image URLs from article
            article = driver.find_element("css selector", "#widget_1559 article")
            image_elements = article.find_elements("css selector", ".layout-ratio img")
            print(f"🖼️ Found {len(image_elements)} images in article {idx}")

            valid_img_urls = []
            for img in image_elements:
                img_url = img.get_attribute("src")
                if img_url and "no-image" not in img_url:
                    valid_img_urls.append(img_url)

            # ⛔ Close article tab before image processing
            tab_handles_before = driver.window_handles.copy()
            driver.close()
            driver.switch_to.window(driver.window_handles[0])

            image_paths = []

            # Open all images in new tabs
            for img_url in valid_img_urls:
                driver.execute_script(f"window.open('{img_url}', '_blank');")
                time.sleep(0.3)

            new_tabs = [h for h in driver.window_handles if h not in tab_handles_before]
            for i, tab in enumerate(new_tabs, start=1):
                driver.switch_to.window(tab)
                time.sleep(1)

                if is_cloudflare_challenge(driver):
                    driver.uc_gui_click_captcha()
                    WebDriverWait(driver, 15).until(lambda d: not is_cloudflare_challenge(d))
                    print("✅ Cloudflare bypassed for image")

                try:
                    big_img = driver.find_element("css selector", "body > img")
                    img_filename = f"{slug}_{i}.png"
                    img_path = os.path.join(images_dir, img_filename)
                    big_img.screenshot(img_path)
                    image_paths.append(f"Images/{img_filename}")
                    print(f"📸 Image {i} saved: {img_path}")
                except Exception as e:
                    print(f"⚠️ Failed to screenshot image {i}: {e}")
                driver.close()

            # ⬅️ Back to main tab
            driver.switch_to.window(driver.window_handles[0])

            # 🔄 Update article JSON with image paths
            with open(json_path, "r+", encoding="utf-8") as f:
                data = json.load(f)
                data["images"] = image_paths
                f.seek(0)
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.truncate()

        except Exception as e:
            print(f"⚠️ Failed to scrape article: {link} — {e}")
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
            continue

    except Exception as e:
        print(f"❌ Failed to open tab for {link} — {e}")

driver.quit()
end_time = time.time()

# ⏱️ Show total scraping time
elapsed = end_time - start_time
hours, rem = divmod(elapsed, 3600)
minutes, seconds = divmod(rem, 60)
print(f"\n🎉 Scraping finished in {int(hours)}h {int(minutes)}m {int(seconds)}s.")
