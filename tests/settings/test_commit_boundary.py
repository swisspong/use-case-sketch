"""A successful mutation is already visible to the immediate HTTP refetch."""

import httpx
from sqlalchemy import delete

from app.main import create_app
from app.modules.text_quality.models import TextQualityThresholds
from app.shared.config import Settings, get_settings
from app.shared.deps import get_resources
from app.shared.resources import build_resources


async def test_success_response_is_sent_only_after_commit(engine, database_url):
    settings = Settings(database_url=database_url)
    resources = build_resources(settings)
    app = create_app()
    app.dependency_overrides[get_resources] = lambda: resources
    app.dependency_overrides[get_settings] = lambda: settings
    seen = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as reader:

        async def observed_app(scope, receive, send):
            async def observe(message):
                if (
                    scope["method"] == "PATCH"
                    and message["type"] == "http.response.start"
                    and message["status"] == 200
                ):
                    seen.append(
                        (await reader.get("/text-quality/thresholds")).json()[
                            "max_thai_percent"
                        ]
                    )
                await send(message)

            await app(scope, receive, observe)

        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=observed_app), base_url="http://test"
            ) as writer:
                response = await writer.patch(
                    "/text-quality/thresholds", json={"max_thai_percent": 82}
                )
                assert response.status_code == 200
                assert seen == [82]
        finally:
            async with engine.begin() as connection:
                await connection.execute(delete(TextQualityThresholds))
            await resources.aclose()
