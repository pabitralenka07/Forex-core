"""Conversion history REST endpoints under /v1."""

import csv
import io
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.decimal_utils import parse_decimal_amount, validate_currency_code
from app.core.exceptions import RateSanityError
from app.database.repository import RateRepository
from app.database.session import get_db
from app.schemas.envelope import APIResponse
from app.schemas.history import (
    ConversionHistoryItem,
    ConversionHistoryResponseData,
    RecordConversionRequest,
)

router = APIRouter(prefix="/history", tags=["Conversion History"])


@router.get(
    "",
    response_model=APIResponse[ConversionHistoryResponseData],
    summary="Get Conversion History",
    description="Retrieve paginated conversion history for an anonymous session or user ID.",
)
async def get_history(
    request: Request,
    session_id: str = Query(..., description="Client or user session ID", min_length=1),
    limit: int = Query(50, ge=1, le=200, description="Page size limit"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ConversionHistoryResponseData]:
    """Retrieve historical conversion records."""
    request_id: str = getattr(request.state, "request_id", "unknown")
    repo = RateRepository(db)
    records, total = await repo.get_conversion_history(
        session_id=session_id,
        limit=limit,
        offset=offset,
    )

    items = [
        ConversionHistoryItem.model_validate(
            {
                "id": r.id,
                "session_id": r.session_id,
                "from": r.from_currency,
                "to": r.to_currency,
                "amount": str(r.amount),
                "converted_amount": str(r.converted_amount),
                "rate": str(r.rate),
                "created_at": r.created_at.isoformat(),
            }
        )
        for r in records
    ]

    data = ConversionHistoryResponseData(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        session_id=session_id.strip(),
    )
    return APIResponse.create_success(data=data, request_id=request_id)


@router.post(
    "",
    response_model=APIResponse[ConversionHistoryItem],
    summary="Record Conversion",
    description="Record a completed currency conversion into the session's history log.",
)
async def record_conversion(
    request: Request,
    body: RecordConversionRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ConversionHistoryItem]:
    """Record a conversion event."""
    request_id: str = getattr(request.state, "request_id", "unknown")
    repo = RateRepository(db)

    norm_from = validate_currency_code(body.from_currency)
    norm_to = validate_currency_code(body.to_currency)
    amount_dec = parse_decimal_amount(body.amount)
    converted_dec = parse_decimal_amount(body.converted_amount)
    try:
        rate_dec = Decimal(body.rate.strip())
        if rate_dec <= Decimal("0") or rate_dec.is_nan() or rate_dec.is_infinite():
            raise RateSanityError(f"Invalid rate: {body.rate}")
    except Exception as exc:
        raise RateSanityError(f"Invalid rate value '{body.rate}': {exc}") from exc

    rec = await repo.add_conversion_history(
        session_id=body.session_id,
        from_currency=norm_from,
        to_currency=norm_to,
        amount=amount_dec,
        converted_amount=converted_dec,
        rate=rate_dec,
    )

    item = ConversionHistoryItem.model_validate(
        {
            "id": rec.id,
            "session_id": rec.session_id,
            "from": rec.from_currency,
            "to": rec.to_currency,
            "amount": str(rec.amount),
            "converted_amount": str(rec.converted_amount),
            "rate": str(rec.rate),
            "created_at": rec.created_at.isoformat(),
        }
    )
    return APIResponse.create_success(data=item, request_id=request_id)


@router.delete(
    "",
    response_model=APIResponse[dict[str, int]],
    summary="Clear Conversion History",
    description="Clear all conversion logs for the given session ID.",
)
async def clear_history(
    request: Request,
    session_id: str = Query(..., description="Client or user session ID", min_length=1),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict[str, int]]:
    """Clear history for a session."""
    request_id: str = getattr(request.state, "request_id", "unknown")
    repo = RateRepository(db)
    deleted_count = await repo.clear_conversion_history(session_id=session_id)

    return APIResponse.create_success(
        data={"deleted_count": deleted_count},
        request_id=request_id,
    )


@router.get(
    "/export",
    summary="Export Conversion History (CSV)",
    description="Export complete conversion history as a downloadable CSV file.",
)
async def export_history_csv(
    session_id: str = Query(..., description="Client or user session ID", min_length=1),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Stream or return complete conversion history formatted as standard CSV."""
    repo = RateRepository(db)
    records, _ = await repo.get_conversion_history(session_id=session_id, limit=5000, offset=0)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "From", "To", "Amount", "Converted Amount", "Rate", "Timestamp (UTC)"])

    for r in records:
        writer.writerow(
            [
                r.id,
                r.from_currency,
                r.to_currency,
                str(r.amount),
                str(r.converted_amount),
                str(r.rate),
                r.created_at.isoformat(),
            ]
        )

    csv_content = output.getvalue()
    filename = f"conversion_history_{session_id.strip()[:8]}.csv"

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
