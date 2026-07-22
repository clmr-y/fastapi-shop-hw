from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_buyer, get_current_user, role_forbidden_exception
from app.db_depends import get_async_db
from app.models.products import Product as ProductModel
from app.models.reviews import Review as ReviewModel
from app.models.users import User as UserModel
from app.schemas import Review as ReviewSchema
from app.schemas import ReviewCreate

router = APIRouter(
    prefix="/reviews",
    tags=["reviews"],
)


@router.get("/", response_model=list[ReviewSchema], status_code=status.HTTP_200_OK)
async def get_all_reviews(db: AsyncSession = Depends(get_async_db)):
    """
    Возвращает список всех отзывов.
    """
    result = await db.scalars(
        select(ReviewModel)
        .join(ProductModel)
        .join(UserModel)
        .where(
            UserModel.is_active == True,
            ReviewModel.is_active == True,
            ProductModel.is_active == True,
        )
    )
    reviews = result.all()
    return reviews


@router.get(
    "/{product_id}/reviews",
    response_model=list[ReviewSchema],
    status_code=status.HTTP_200_OK,
)
async def get_product_reviews(
    product_id: int, db: AsyncSession = Depends(get_async_db)
):
    """
    Возвращает список отзывов для указанного товара.
    """
    product = await db.scalar(
        select(ProductModel).where(
            ProductModel.is_active == True,
            ProductModel.id == product_id,
        )
    )

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found or inactive",
        )

    result = await db.scalars(
        select(ReviewModel).where(
            UserModel.is_active == True,
            ReviewModel.is_active == True,
            ReviewModel.id == product_id,
        )
    )

    reviews = result.all()
    return reviews


async def update_product_rating(product_id, db: AsyncSession) -> None:
    """
    Обнавляет рейтинг товара.
    """
    new_rating = await db.scalar(
        select(func.coalesce(func.avg(ReviewModel.grade), 0)).where(
            ReviewModel.product_id == product_id, ReviewModel.is_active == True
        )
    )

    await db.execute(
        update(ProductModel)
        .where(ProductModel.id == product_id)
        .values(rating=new_rating)
    )


@router.post("/", response_model=ReviewSchema, status_code=status.HTTP_201_CREATED)
async def create_review(
    review: ReviewCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: UserModel = Depends(get_current_buyer),
):
    """
    Создает новый отзыв для товара.
    """
    product = await db.scalar(
        select(ProductModel).where(
            ProductModel.id == review.product_id, ProductModel.is_active == True
        )
    )
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found or inactive",
        )

    db_review = ReviewModel(**review.model_dump(), user_id=current_user.id)
    db.add(db_review)
    await db.flush()

    await update_product_rating(review.product_id, db)
    await db.commit()
    await db.refresh(db_review)

    return db_review


@router.delete("/reviews/{review_id}", status_code=status.HTTP_200_OK)
async def delete_review(
    review_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: UserModel = Depends(get_current_user),
):
    """
    Удаляет товар по его ID (логичесское удаление).
    """
    if not (current_user.role == "buyer" or current_user.role == "admin"):
        raise role_forbidden_exception(current_user.role)

    review = await db.scalar(
        select(ReviewModel).where(
            ReviewModel.is_active == True,
            ReviewModel.id == review_id,
        )
    )

    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found or inactive",
        )

    if current_user.id != review.user_id and current_user.role == "buyer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own reviews",
        )

    review.is_active = False
    await db.flush()
    await update_product_rating(review.product_id, db)
    await db.commit()

    return {"message": "Review deleted"}
