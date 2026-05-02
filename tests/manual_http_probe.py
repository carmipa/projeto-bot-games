import httpx
import asyncio
import certifi

async def test_sites():
    urls = [
        "https://www.epicgames.com/",
        "https://www.unrealengine.com/",
        "https://www.koeitecmo.com/",
        "https://www.gamespot.com/"
    ]
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    async with httpx.AsyncClient(headers={"User-Agent": ua}, timeout=10, follow_redirects=True, verify=certifi.where()) as client:
        for url in urls:
            try:
                resp = await client.get(url)
                print(f"URL: {url} | Status: {resp.status_code}")
            except Exception as e:
                print(f"URL: {url} | Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_sites())
