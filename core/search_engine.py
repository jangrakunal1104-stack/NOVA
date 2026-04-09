import requests
import os

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

def search_web(query: str, max_results: int = 5):
    if not TAVILY_API_KEY:
        return []

    try:
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "advanced",
                "max_results": max_results,
            },
            timeout=10
        )

        data = response.json()

        results = []
        for r in data.get("results", []):
            content = r.get("content", "")
            if content and len(content) >= 50:
                results.append({
                    "title": r.get("title"),
                    "content": content
                })

        return results

    except:
        return []