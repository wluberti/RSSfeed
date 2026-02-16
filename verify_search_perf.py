
import time
from web_search import search_feeds
import timeit

start_time = time.time()
print("Starting search for 'Webwereld'...")
results = search_feeds("Webwereld")
end_time = time.time()

print(f"Search took {end_time - start_time:.2f} seconds")
print(f"Found {len(results)} results")
for r in results:
    print(f"- {r['title']} ({r['feed_url']})")
