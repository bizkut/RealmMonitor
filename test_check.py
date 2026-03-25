import asyncio

async def test():
    args = ['us-gundrak']
    query = " ".join(args).strip()
    parts = query.split("-")
    
    valid_versions = ['retail', 'classic', 'classic-era', 'sod']
    if parts[0].lower() in valid_versions:
        version = parts.pop(0).lower()
        if version == 'sod':
            version = 'classic-era'
    else:
        version = 'retail'
        
    if len(parts) < 2:
        print("Invalid format.")
        return
        
    region = parts.pop(0).lower()
    valid_regions = ['us', 'eu', 'kr', 'tw']
    if region not in valid_regions:
        print(f"Invalid region '{region}'.")
        return
        
    search_term = "-".join(parts).lower()
    print(f"version: {version}, region: {region}, search_term: {search_term}")

asyncio.run(test())
