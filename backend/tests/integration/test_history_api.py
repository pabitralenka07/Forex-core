"""Integration tests for conversion history, CSV export, and favorites REST endpoints."""

import csv
import io
import uuid
from decimal import Decimal

import pytest
import respx
from httpx import AsyncClient, Response

FRANKFURTER_URL = "https://api.frankfurter.dev/v1"


@pytest.mark.asyncio
async def test_record_and_get_history(async_client: AsyncClient) -> None:
    """Test manual recording and paginated retrieval of conversion history."""
    session_id = f"integ_sess_{uuid.uuid4().hex[:8]}"

    # 1. Post a conversion record
    post_res = await async_client.post(
        "/v1/history",
        json={
            "session_id": session_id,
            "from": "USD",
            "to": "EUR",
            "amount": "100.00",
            "converted_amount": "92.00",
            "rate": "0.9200000000",
        },
    )
    assert post_res.status_code == 200
    post_data = post_res.json()
    assert post_data["success"] is True
    assert post_data["data"]["from"] == "USD"
    assert post_data["data"]["to"] == "EUR"
    assert Decimal(post_data["data"]["amount"]) == Decimal("100.00")

    # 2. Get history
    get_res = await async_client.get("/v1/history", params={"session_id": session_id})
    assert get_res.status_code == 200
    get_payload = get_res.json()
    assert get_payload["success"] is True
    assert get_payload["data"]["total"] == 1
    items = get_payload["data"]["items"]
    assert items[0]["session_id"] == session_id
    assert items[0]["from"] == "USD"
    assert items[0]["to"] == "EUR"


@pytest.mark.asyncio
async def test_clear_history(async_client: AsyncClient) -> None:
    """Test clearing conversion history for a session."""
    session_id = f"integ_sess_clear_{uuid.uuid4().hex[:8]}"

    # Add item
    await async_client.post(
        "/v1/history",
        json={
            "session_id": session_id,
            "from": "GBP",
            "to": "USD",
            "amount": "50.00",
            "converted_amount": "65.00",
            "rate": "1.3000000000",
        },
    )

    # Clear
    del_res = await async_client.delete("/v1/history", params={"session_id": session_id})
    assert del_res.status_code == 200
    assert del_res.json()["data"]["deleted_count"] >= 1

    # Verify empty
    get_res = await async_client.get("/v1/history", params={"session_id": session_id})
    assert get_res.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_export_history_csv(async_client: AsyncClient) -> None:
    """Test CSV export of conversion history."""
    session_id = f"integ_sess_csv_{uuid.uuid4().hex[:8]}"

    await async_client.post(
        "/v1/history",
        json={
            "session_id": session_id,
            "from": "EUR",
            "to": "JPY",
            "amount": "20.00",
            "converted_amount": "3200",
            "rate": "160.0000000000",
        },
    )

    export_res = await async_client.get("/v1/history/export", params={"session_id": session_id})
    assert export_res.status_code == 200
    assert "text/csv" in export_res.headers["content-type"]
    assert "attachment; filename=" in export_res.headers["content-disposition"]

    csv_reader = csv.reader(io.StringIO(export_res.text))
    rows = list(csv_reader)
    assert len(rows) >= 2  # Header + at least 1 record
    header = rows[0]
    assert header == ["ID", "From", "To", "Amount", "Converted Amount", "Rate", "Timestamp (UTC)"]
    assert rows[1][1] == "EUR"
    assert rows[1][2] == "JPY"


@pytest.mark.asyncio
@respx.mock
async def test_convert_auto_records_to_history(async_client: AsyncClient) -> None:
    """Test that GET /v1/convert automatically logs to history when session_id is provided."""
    session_id = f"sess_auto_record_{uuid.uuid4().hex[:8]}"

    respx.get(f"{FRANKFURTER_URL}/latest").mock(
        return_value=Response(
            200,
            json={
                "amount": 1.0,
                "base": "USD",
                "date": "2024-01-15",
                "rates": {"EUR": 0.92},
            },
        )
    )

    # Convert with session_id
    conv_res = await async_client.get(
        "/v1/convert",
        params={
            "from": "USD",
            "to": "EUR",
            "amount": "150.00",
            "session_id": session_id,
        },
    )
    assert conv_res.status_code == 200

    # Verify conversion was saved in history
    hist_res = await async_client.get("/v1/history", params={"session_id": session_id})
    assert hist_res.status_code == 200
    hist_data = hist_res.json()["data"]
    assert hist_data["total"] == 1
    assert hist_data["items"][0]["from"] == "USD"
    assert hist_data["items"][0]["to"] == "EUR"
    assert Decimal(hist_data["items"][0]["amount"]) == Decimal("150.00")
    assert Decimal(hist_data["items"][0]["converted_amount"]) == Decimal("138.00")


@pytest.mark.asyncio
async def test_favorites_api_lifecycle(async_client: AsyncClient) -> None:
    """Test adding, listing, and removing favorites through REST endpoints."""
    session_id = f"sess_fav_{uuid.uuid4().hex[:8]}"

    # Add favorite
    add_res = await async_client.post(
        "/v1/favorites",
        json={"session_id": session_id, "currency_code": "GBP"},
    )
    assert add_res.status_code == 200
    assert add_res.json()["data"]["code"] == "GBP"

    # List favorites
    list_res = await async_client.get("/v1/favorites", params={"session_id": session_id})
    assert list_res.status_code == 200
    favs = list_res.json()["data"]["favorites"]
    assert len(favs) == 1
    assert favs[0]["code"] == "GBP"

    # Remove favorite
    del_res = await async_client.delete(f"/v1/favorites/GBP?session_id={session_id}")
    assert del_res.status_code == 200
    assert del_res.json()["data"]["removed"] is True

    # Verify empty
    list_empty = await async_client.get("/v1/favorites", params={"session_id": session_id})
    assert len(list_empty.json()["data"]["favorites"]) == 0
