import asyncio
import json

import httpx

from bot.ai import AIQueryAnalyzer


def test_ai_understanding_accepts_only_known_systems():
    async def run():
        async def handler(request: httpx.Request):
            body = json.loads(request.content)
            assert body["messages"][0]["role"] == "system"
            return httpx.Response(200, json={
                "choices": [{"message": {"content": '{"system":"rsed","search_query":"подписание в РСЭД"}'}}]
            })

        analyzer = AIQueryAnalyzer("test", "https://ai.example/v1", "model", {"rsed": "РСЭД"})
        await analyzer.client.aclose()
        analyzer.client = httpx.AsyncClient(
            base_url="https://ai.example/v1/", transport=httpx.MockTransport(handler)
        )
        result = await analyzer.understand("а как подписать?", ["Работаю в РСЭД"], "rsed")
        await analyzer.close()
        assert result.system == "rsed"
        assert result.search_query == "подписание в РСЭД"

    asyncio.run(run())
