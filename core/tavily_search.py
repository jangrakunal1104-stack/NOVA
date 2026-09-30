# core/tavily_search.py
import os
from typing import List, Dict

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv is optional: TAVILY_API_KEY can also be exported
    # directly in the environment (this is a no-op if desktop.py already
    # loaded the .env file for this process).
    pass

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None
    print("[TAVILY] Package 'tavily-python' not installed. Run: pip install tavily-python")


class TavilySearch:
    def __init__(self):
        self.api_key = os.getenv("TAVILY_API_KEY")
        if not self.api_key:
            print("[TAVILY] Warning: TAVILY_API_KEY not found in environment")
        if TavilyClient is None:
            self.client = None
        else:
            self.client = TavilyClient(api_key=self.api_key) if self.api_key else None

    def search(self, query: str, max_results: int = 5) -> List[Dict]:
        """Perform web search using Tavily. Returns list of {title, url?, content}."""
        if not self.client:
            return [{
                "title": "Search unavailable",
                "content": (
                    "Tavily is not configured. Set TAVILY_API_KEY in your environment "
                    "and install tavily-python (pip install tavily-python)."
                )
            }]

        try:
            response = self.client.search(
                query=query,
                search_depth="advanced",
                max_results=max_results,
                include_answer=True,
                include_raw_content=False
            )

            results = []
            if response.get("answer"):
                results.append({
                    "title": "Direct Answer",
                    "content": response["answer"]
                })

            for res in response.get("results", []):
                results.append({
                    "title": res.get("title", "No Title"),
                    "url": res.get("url"),
                    "content": (res.get("content") or "")[:800]
                })

            if not results:
                results.append({
                    "title": "No results",
                    "content": f"No search results found for: {query}"
                })

            return results
        except Exception as e:
            return [{"title": "Search Error", "content": str(e)}]

    def format_for_prompt(self, results: List[Dict]) -> str:
        """Turn search results into a clean block for the LLM."""
        if not results:
            return "No web search results available."

        lines = [
            "=== LIVE WEB SEARCH RESULTS ===",
            "Use these facts to answer. Prefer this over your training data for current events."
        ]
        for i, r in enumerate(results, 1):
            title = r.get("title", "Result")
            content = r.get("content", "")
            url = r.get("url")
            lines.append(f"\n[{i}] {title}")
            if url:
                lines.append(f"Source: {url}")
            lines.append(content)
        lines.append("\n=== END SEARCH RESULTS ===")
        return "\n".join(lines)