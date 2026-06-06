import requests

# DCAT US 1.1 feed - returns all datasets as JSON
url = "https://opendata.esrichina.hk/api/feed/dcat-us/1.1.json"
data = requests.get(url).json()

# Filter by Security tag
security_datasets = [
    ds for ds in data.get("dataset", [])
    if "Security" in ds.get("keyword", [])
]

for ds in security_datasets:
    print(f"Title: {ds['title']}")
    print(f"Description: {ds['description']}")
    print(f"Landing page: {ds['landingPage']}")
    # Data download links
    for dist in ds.get("distribution", []):
        print(f"  Download: {dist.get('downloadURL')} ({dist.get('mediaType')})")
    print()