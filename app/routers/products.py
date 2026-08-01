import uuid
from datetime import datetime
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_seller
from app.db_depends import get_async_db
from app.models.categories import Category as CategoryModel
from app.models.products import Product as ProductModel
from app.models.users import User as UserModel
from app.schemas import Product as ProductSchema
from app.schemas import ProductCreate, ProductList

BASE_DIR = Path(__file__).resolve().parent.parent.parent
MEDIA_ROOT = BASE_DIR / "media" / "products"
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE = 2 * 1024 * 1024  # 2 097 152 байт

async def save_product_image(file: UploadFile) -> str:
    """
    Сохраняет изображение товара и возвращает относительный URL.
    """
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only JPG, PNG or WebP images are allowed")

    content = await file.read()
    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Image is too large")

    extension = Path(file.filename or "").suffix.lower() or ".jpg"
    file_name = f"{uuid.uuid4()}{extension}"
    file_path = MEDIA_ROOT / file_name
    file_path.write_bytes(content)

    return f"/media/products/{file_name}"

def remove_product_image(url: str | None) -> None:
    """
    Удаляет файл изображения, если он существует.
    """
    if not url:
        return
    relative_path = url.lstrip("/")
    file_path = BASE_DIR / relative_path
    if file_path.exists():
        file_path.unlink()

router = APIRouter(
    prefix="/products",
    tags=["products"],
)


@router.get("/", response_model=ProductList, status_code=status.HTTP_200_OK)
async def get_all_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category_id: int | None = Query(None, description="ID категории для фильтрации"),
    search: str | None = Query(None, description="Поиск по названию товара"),
    min_price: float | None = Query(None, ge=0, description="Минимальная цена товара"),
    max_price: float | None = Query(None, ge=0, description="Максимальная цена товара"),
    in_stock: bool | None = Query(None, description="true — только товары в наличии, false — только без остатка"),
    seller_id: int | None = Query(None, description="ID продавца для фильтрации"),
    ordered_date: bool | None = Query(None, description="Сортировка по дате"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Возвращает список всех товаров.
    """
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="min_price не может быть больше max_price",
    )

    filters = [ProductModel.is_active == True]
    orders = [ProductModel.id]

    if category_id is not None:
        filters.append(ProductModel.category_id == category_id)
    if min_price is not None:
        filters.append(ProductModel.price >= min_price)
    if max_price is not None:
        filters.append(ProductModel.price <= max_price)
    if in_stock is not None:
        filters.append(ProductModel.stock > 0 if in_stock else ProductModel.stock == 0)
    if seller_id is not None:
        filters.append(ProductModel.seller_id == seller_id)
    if ordered_date is not None:
        orders.append(ProductModel.created_at)

    rank_col = None
    if search is not None:
        search_value = search.strip().lower()
        if search_value:
            ts_query = func.websearch_to_tsquery("english", search_value)
            filters.append(ProductModel.tsv.op("@@")(ts_query))
            rank_col = func.ts_rank_cd(ProductModel.tsv, ts_query).label("rank")

    total_stmt = (
        select(func.count())
        .select_from(ProductModel)
        .where(*filters)
    )

    total = await db.scalar(total_stmt) or 0

    if rank_col is not None:
        products_stmt = (
            select(ProductModel, rank_col)
            .where(*filters)
            .order_by(desc(rank_col), *orders)
            .offset((page-1)*page_size)
            .limit(page_size)
        )
        result = await db.execute(products_stmt)
        rows = result.all()
        items = [row[0] for row in rows]
    else:
        products_stmt = (
            select(ProductModel)
            .where(*filters)
            .order_by(*orders)
            .offset((page-1)*page_size)
            .limit(page_size)
        )
        items = (await db.scalars(products_stmt)).all()

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.post("/", response_model=ProductSchema, status_code=status.HTTP_201_CREATED)
async def create_product(
    product: ProductCreate = Depends(ProductCreate.as_form),
    image: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_async_db),
    current_user: UserModel = Depends(get_current_seller),
):
    """
    Создаёт новый товар.
    """
    result = await db.scalars(
        select(CategoryModel).where(
            CategoryModel.id == product.category_id, CategoryModel.is_active == True
        )
    )
    category = result.first()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category not found or inactive",
        )

    image_url = await save_product_image(image) if image else None

    db_product = ProductModel(
        **product.model_dump(), 
        seller_id=current_user.id,
        image_url=image_url,
    )

    db.add(db_product)
    await db.commit()
    await db.refresh(db_product)
    return db_product


@router.get("/category/{category_id}", response_model=list[ProductSchema])
async def get_products_by_category(
    category_id: int, db: AsyncSession = Depends(get_async_db)
):
    """
    Возвращает список активных товаров в указанной категории по её ID.
    """
    result = await db.scalars(
        select(CategoryModel).where(
            CategoryModel.id == category_id, CategoryModel.is_active == True
        )
    )
    category = result.first()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found or inactive",
        )

    result = await db.scalars(
        select(ProductModel).where(
            ProductModel.category_id == category_id, ProductModel.is_active == True
        )
    )
    products = result.all()
    return products


@router.get("/{product_id}", response_model=ProductSchema)
async def get_product(product_id: int, db: AsyncSession = Depends(get_async_db)):
    """
    Возвращает детальную информацию о товаре по его ID.
    """
    result = await db.scalars(
        select(ProductModel).where(
            ProductModel.id == product_id, ProductModel.is_active == True
        )
    )
    product = result.first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found or inactive",
        )

    result = await db.scalars(
        select(CategoryModel).where(
            CategoryModel.id == product.category_id, CategoryModel.is_active == True
        )
    )
    category = result.first()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category not found or inactive",
        )

    return product


@router.put("/{product_id}", response_model=ProductSchema)
async def update_product(
    product_id: int,
    product: ProductCreate = Depends(ProductCreate.as_form),
    image: UploadFile | None = File(None),
    current_user: UserModel = Depends(get_current_seller),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Обновляет товар по его ID.
    """
    result = await db.scalars(
        select(ProductModel).where(
            ProductModel.id == product_id, ProductModel.is_active == True
        )
    )
    db_product = result.first()

    if not db_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found or inactive",
        )

    if db_product.seller_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own products",
        )

    result = await db.scalars(
        select(CategoryModel).where(
            CategoryModel.id == product.category_id, CategoryModel.is_active == True
        )
    )
    category = result.first()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category not found or inactive",
        )

    await db.execute(
        update(ProductModel)
        .where(ProductModel.id == product_id)
        .values(**product.model_dump())
    )

    if image: 
        remove_product_image(db_product.image_url)
        db_product.image_url = await save_product_image(image)

    await db.commit()
    await db.refresh(db_product)
    return db_product


@router.delete(
    "/{product_id}", response_model=ProductSchema, status_code=status.HTTP_200_OK
)
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: UserModel = Depends(get_current_seller),
):
    """
    Удаляет товар по его ID (логическое удаление).
    """
    result = await db.scalars(
        select(ProductModel).where(
            ProductModel.id == product_id, ProductModel.is_active == True
        )
    )
    product = result.first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found or inactive",
        )

    if product.seller_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own products",
        )

    remove_product_image(product.image_url)

    await db.execute(
        update(ProductModel)
        .where(ProductModel.id == product_id)
        .values(image_url=None, is_active=False)
    )

    await db.commit()
    await db.refresh(product)
    return product
