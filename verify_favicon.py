
from feed_service import fetch_feed

print("Fetching feed for nu.nl...")
result = fetch_feed("https://www.nu.nl/rss")
if result:
    meta = result["meta"]
    print(f"Title: {meta['title']}")
    print(f"Image URL: {meta['image_url']}")
    if "google.com/s2/favicons" in meta["image_url"]:
        print("SUCCESS: Google Favicon service used.")
    elif meta["image_url"]:
        print("SUCCESS: Native feed image found.")
    else:
        print("FAILURE: No image URL found.")
else:
    print("FAILURE: Could not fetch feed.")
