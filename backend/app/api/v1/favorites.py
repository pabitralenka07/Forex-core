"""Favorites management REST endpoints under /v1."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.decimal_utils import validate_currency_code
from app.database.repository import RateRepository
from app.database.session import get_db
from app.schemas.envelope import APIResponse
from app.schemas.favorites import AddFavoriteRequest, FavoriteItem, FavoritesResponseData

router = APIRouter(prefix="/favorites", tags=["Favorite Currencies"])


@router.get(
    "",
    response_model=APIResponse[FavoritesResponseData],
    summary="Get Favorite Currencies",
    description="Retrieve all favorite currencies saved by the anonymous session ID or user.",
)
async def get_favorites(
    request: Request,
    session_id: str = Query(..., description="Client or user session ID", min_length=1),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[FavoritesResponseData]:
    """Retrieve saved favorite currencies."""
    request_id: str = getattr(request.state, "request_id", "unknown")
    repo = RateRepository(db)
    fav_currencies = await repo.get_favorites(session_id=session_id)

    items = [
        FavoriteItem(
            code=c.code,
            name=c.name,
            symbol=c.symbol,
            minor_units=c.minor_units,
        )
        for c in fav_currencies
    ]

    data = FavoritesResponseData(
        favorites=items,
        count=len(items),
        session_id=session_id.strip(),
    )
    return APIResponse.create_success(data=data, request_id=request_id)


@router.post(
    "",
    response_model=APIResponse[FavoriteItem],
    summary="Add Favorite Currency",
    description="Add a supported currency to the user's favorites list.",
)
async def add_favorite(
    request: Request,
    body: AddFavoriteRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[FavoriteItem]:
    """Add currency to favorites."""
    request_id: str = getattr(request.state, "request_id", "unknown")
    repo = RateRepository(db)
    norm_code = validate_currency_code(body.currency_code)

    await repo.add_favorite(session_id=body.session_id, currency_code=norm_code)
    curr = await repo.ensure_currency_exists(norm_code)

    item = FavoriteItem(
        code=curr.code,
        name=curr.name,
        symbol=curr.symbol,
        minor_units=curr.minor_units,
    )
    return APIResponse.create_success(data=item, request_id=request_id)


@router.delete(
    "/{currency_code}",
    response_model=APIResponse[dict[str, bool]],
    summary="Remove Favorite Currency",
    description="Remove a currency from the user's favorites list.",
)
async def remove_favorite(
    request: Request,
    currency_code: str,
    session_id: str = Query(..., description="Client or user session ID", min_length=1),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict[str, bool]]:
    """Remove currency from favorites."""
    request_id: str = getattr(request.state, "request_id", "unknown")
    repo = RateRepository(db)
    norm_code = validate_currency_code(currency_code)

    removed = await repo.remove_favorite(session_id=session_id, currency_code=norm_code)
    return APIResponse.create_success(
        data={"removed": removed},
        request_id=request_id,
    )
