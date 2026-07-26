from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CategoryCreate(BaseModel):
    """
    Модель для создания и обновления категории.
    Используется в POST и PUT запросах.
    """

    name: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Название категории (3-50 символов)",
    )
    parent_id: int | None = Field(
        None, description="ID родительской категории, если есть"
    )


class Category(BaseModel):
    """
    Модель для ответа с данными категории.
    Используется в GET-запросах.
    """

    id: int = Field(..., description="Уникальный идентификатор категории")
    name: str = Field(..., description="Название категории")
    parent_id: int | None = Field(
        None, description="ID родительской категории, если есть"
    )
    is_active: bool = Field(..., description="Активность категории")

    model_config = ConfigDict(from_attributes=True)


class ProductCreate(BaseModel):
    """
    Модель для создания и обновления товара.
    Используется в POST и PUT запросах.
    """

    name: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Название товара (3-100 символов)",
    )
    description: str | None = Field(
        None, max_length=500, description="Описание товара (до 500 символов)"
    )
    price: Decimal = Field(
        ..., gt=0, description="Цена товара (больше 0)", decimal_places=2
    )
    image_url: str | None = Field(
        None, max_length=200, description="URL изображения товара"
    )
    stock: int = Field(
        ..., ge=0, description="Количество товара на складе (0 или больше)"
    )
    category_id: int = Field(..., description="ID категории, к которой относится товар")


class Product(BaseModel):
    """
    Модель для ответа с данными товара.
    Используется в GET-запросах.
    """

    id: int = Field(..., description="Уникальный идентификатор товара")
    name: str = Field(..., description="Название товара")
    description: str | None = Field(None, description="Описание товара")
    price: Decimal = Field(
        ..., description="Цена товара в рублях", gt=0, decimal_places=2
    )
    image_url: str | None = Field(None, description="URL изображения товара")
    stock: int = Field(..., description="Количество товара на складе")
    rating: int = Field(..., description="Оценка товара")
    category_id: int = Field(..., description="ID категории")
    is_active: bool = Field(..., description="Активность товара")

    model_config = ConfigDict(from_attributes=True)


class Review(BaseModel):
    """
    Модель для ответа с данными отзывов о товаре.
    Используется в GET-запросах
    """

    id: int = Field(..., description="Уникальный идентификатор отзыва")
    user_id: int = Field(..., description="ID пользователя, который написал отзыв")
    product_id: int = Field(..., description="ID товара, которому написали отзыв")
    comment: str = Field(..., description="Текст комментария")
    comment_date: datetime = Field(..., description="Дата и время создания отзыва")
    grade: int = Field(..., description="Рейтинг 1-5")
    is_active: bool = Field(..., description="Активность отзыва")


class ReviewCreate(BaseModel):
    """
    Модель для создания отзывов о товаре.
    Используется в POST и PUT запросах
    """

    product_id: int = Field(description="ID товара")
    comment: str = Field(description="Текст комментария")
    grade: int = Field(description="Рейтинг товара 1-5", ge=1, le=5)


class UserCreate(BaseModel):
    """Млдель для создания пользователей."""

    email: EmailStr = Field(description="Email пользователя")
    password: str = Field(min_length=8, description="Пароль (минимум 8 символов)")
    role: str = Field(
        default="buyer",
        pattern="^(buyer|seller)$",
        description="Роль: 'buyer' или 'seller'",
    )


class User(BaseModel):
    """Модель с данными о пользователе"""

    id: int
    email: EmailStr
    is_active: bool
    role: str
    model_config = ConfigDict(from_attributes=True)


class RefreshTokenRequest(BaseModel):
    refresh_token: str

class ProductList(BaseModel):
    """
    Список пагинации для товаров.
    """
    items: list[Product] = Field(description="Товары для текущей страницы")
    total: int = Field(ge=0, description="Общее количество товаров")
    page: int = Field(ge=1, description="Номер текущей страницы")
    page_size: int = Field(ge=1, description="Количество элементов на странице")
    
    # Для чтения из ORM-объектов
    model_config = ConfigDict(from_attributes=True) 

class CartItemBase(BaseModel):
    product_id: int = Field(description="ID товара")
    quantity: int = Field(ge=1, description="Количество товара")

class CartItemCreate(CartItemBase):
    """Модель для добавления нового товара в корзину."""
    pass

class CartItemUpdate(BaseModel):
    """Модель для обновления количества товара в корзине."""
    quantity: int = Field(..., ge=1, description="Новое количество товара")

class CartItem(BaseModel):
    """Товар в корзине с данными продукта."""
    id: int = Field(..., description="ID позиции корзины")
    quantity: int = Field(..., ge=1, description="Количество товара")
    product: Product = Field(..., description="Информация о товаре")

    model_config = ConfigDict(from_attributes=True)

class Cart(BaseModel):
    """Полная информация о корзине пользователя."""
    user_id: int = Field(..., description="ID пользователя")
    items: list[CartItem] = Field(default_factory=list, description="Содержимое корзины")
    total_quantity: int = Field(..., ge=0, description="Общее количество товаров")
    total_price: Decimal = Field(..., ge=0, description="Общая стоимость товаров")

    model_config = ConfigDict(from_attributes=True)
