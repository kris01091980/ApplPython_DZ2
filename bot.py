import os
import logging
from typing import Any

import aiohttp

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Message, Update
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import StatesGroup, State

# Настройка логгирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """
    Middleware для логгирования
    """

    async def __call__(self, handler, event: Update, data: dict):
        # Логгирование сообщений пользователя
        if event.message and isinstance(event.message, Message) and event.message.text:
            user_id = event.message.from_user.id
            username = event.message.from_user.username or "Неизвестный пользователь"
            text = event.message.text
            logger.info(f"Пользователь {user_id} (@{username}) написал: {text}")

        # Передача события дальше
        return await handler(event, data)


async def get_weather(city: str) -> Any | None:
    """
    Запрашивает текущую температуру в указанном городе с использованием OpenWeatherMap API.

    :param city: Название города
    :return: Температура в градусах Цельсия
    """
    weather_api_url = "http://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": WEATHER_API_KEY,
        "units": "metric",
        "lang": "ru"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(weather_api_url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                return data["main"]["temp"]
            else:
                logger.error(f"Ошибка получения погоды для города {city}: {response.status}")
                return None


# Загрузка переменных из .env
load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
FOOD_API_URL = "https://world.openfoodfacts.org/cgi/search.pl"

if not API_TOKEN:
    raise ValueError("Токен API для Telegram бота не найден. Убедитесь, что API_TOKEN указан в .env файле.")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
dp.update.middleware(LoggingMiddleware())

# Временное хранилище данных пользователей
users = {}


# Состояния для создания профиля
class ProfileState(StatesGroup):
    weight = State()
    height = State()
    age = State()
    activity = State()
    city = State()


# Состояния для логирования еды
class FoodLoggingState(StatesGroup):
    waiting_for_quantity = State()


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я помогу тебе следить за водой, калориями и тренировками. "
        "Начни с настройки профиля: /set_profile."
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "Список доступных команд:\n"
        "/start - Начать работу с ботом\n"
        "/set_profile - Настройка профиля пользователя\n"
        "/log_water <количество> - Запись выпитой воды (в мл)\n"
        "/log_food <название продукта> - Запись еды\n"
        "/log_workout <тип тренировки> <время (мин)> - Запись тренировок\n"
        "/check_progress - Проверить прогресс по воде и калориям\n"
        "/help - Список доступных команд"
    )


@dp.message(Command("set_profile"))
async def cmd_set_profile(message: Message, state: FSMContext):
    await state.set_state(ProfileState.weight)
    await message.answer("Введите ваш вес (в кг):")


@dp.message(ProfileState.weight)
async def set_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text)
        await state.update_data(weight=weight)
        await state.set_state(ProfileState.height)
        await message.answer("Введите ваш рост (в см):")
    except ValueError:
        await message.answer("Введите корректное значение веса.")


@dp.message(ProfileState.height)
async def set_height(message: Message, state: FSMContext):
    try:
        height = float(message.text)
        await state.update_data(height=height)
        await state.set_state(ProfileState.age)
        await message.answer("Введите ваш возраст:")
    except ValueError:
        await message.answer("Введите корректное значение роста.")


@dp.message(ProfileState.age)
async def set_age(message: Message, state: FSMContext):
    try:
        age = int(message.text)
        await state.update_data(age=age)
        await state.set_state(ProfileState.activity)
        await message.answer("Сколько минут активности у вас в день?")
    except ValueError:
        await message.answer("Введите корректное значение возраста.")


@dp.message(ProfileState.activity)
async def set_activity(message: Message, state: FSMContext):
    try:
        activity = int(message.text)
        await state.update_data(activity=activity)
        await state.set_state(ProfileState.city)
        await message.answer("В каком городе вы находитесь?")
    except ValueError:
        await message.answer("Введите корректное значение активности.")


@dp.message(ProfileState.city)
async def set_city(message: Message, state: FSMContext):
    city = message.text
    data = await state.get_data()

    # Получение текущей температуры
    temperature = await get_weather(city)
    if temperature is None:
        await message.answer(
            "Не удалось получить данные о погоде для указанного города. Попробуйте ввести другой город."
        )
        return

    # Рассчёт нормы воды с учётом температуры
    extra_water = 500 if temperature > 25 else 0
    water_goal = round(data["weight"] * 30 + data["activity"] / 30 * 500 + extra_water, 3)
    calorie_goal = round(10 * data["weight"] + 6.25 * data["height"] - 5 * data["age"], 3)

    users[message.from_user.id] = {
        "weight": data["weight"],
        "height": data["height"],
        "age": data["age"],
        "activity": data["activity"],
        "city": city,
        "water_goal": water_goal,
        "calorie_goal": calorie_goal,
        "logged_water": 0,
        "logged_calories": 0,
        "burned_calories": 0,
    }

    await state.clear()
    await message.answer(
        f"Ваш профиль настроен! Норма воды: {water_goal:.1f} мл в день (температура: {temperature}°C). "
        f"Цель калорий: {calorie_goal:.1f} ккал в день."
    )



@dp.message(Command("log_water"))
async def cmd_log_water(message: Message):
    user_data = users.get(message.from_user.id)
    if not user_data:
        await message.answer("Сначала настройте профиль с помощью команды /set_profile.")
        return

    try:
        amount = int(message.text.split()[1])
        user_data["logged_water"] += amount
        remaining = max(0, user_data["water_goal"] - user_data["logged_water"])
        await message.answer(
            f"Записано: {amount} мл. Выпито: {user_data['logged_water']} мл из {user_data['water_goal']} мл.\n"
            f"Осталось: {remaining} мл."
        )
    except (ValueError, IndexError):
        await message.answer("Введите количество воды после команды. Пример: /log_water 500")


@dp.message(Command("log_workout"))
async def cmd_log_workout(message: Message):
    user_data = users.get(message.from_user.id)
    if not user_data:
        await message.answer("Сначала настройте профиль с помощью команды /set_profile.")
        return

    workout_data = message.text.split()[1:]  # Извлекаем данные после команды
    if len(workout_data) < 2:
        await message.answer(
            "Введите тип тренировки и длительность в минутах. Пример: /log_workout бег 30\n\n"
            "Доступные типы тренировок:\n"
            "- бег\n"
            "- плавание\n"
            "- йога\n"
            "- велосипед\n"
            "- другая (общий расчёт: 5 ккал/мин)"
        )
        return

    try:
        workout_type = workout_data[0]  # Тип тренировки
        duration = int(workout_data[1])  # Длительность в минутах
        # Примерное количество сожжённых калорий за минуту
        calories_per_minute = {
            "бег": 10,
            "плавание": 8,
            "йога": 4,
            "велосипед": 6,
        }
        burned_calories = calories_per_minute.get(workout_type.lower(), 5) * duration  # Расчёт калорий
        user_data["burned_calories"] += burned_calories

        # Учитываем дополнительный расход воды за тренировку (200 мл на 30 минут)
        additional_water = (duration // 30) * 200
        user_data["logged_water"] += additional_water

        await message.answer(
            f"🏋️‍ Тренировка: {workout_type.capitalize()} {duration} минут.\n"
            f"Сожжено: {burned_calories} ккал.\n"
            f"Рекомендуется дополнительно выпить: {additional_water} мл воды."
        )
    except ValueError:
        await message.answer("Введите корректную длительность тренировки в минутах. Пример: /log_workout бег 30")


@dp.message(Command("log_food"))
async def cmd_log_food(message: Message, state: FSMContext):
    user_data = users.get(message.from_user.id)
    if not user_data:
        await message.answer("Сначала настройте профиль с помощью команды /set_profile.")
        return

    food_name = " ".join(message.text.split()[1:])
    if not food_name:
        await message.answer("Введите название продукта после команды. Пример: /log_food банан")
        return

    # Запрос информации о продукте
    async with aiohttp.ClientSession() as session:
        async with session.get(FOOD_API_URL,
                               params={"action": "process", "search_terms": food_name, "json": "true"}) as response:
            if response.status == 200:
                data = await response.json()
                products = data.get("products", [])
                if products:
                    first_product = products[0]
                    calories = first_product.get("nutriments", {}).get("energy-kcal_100g", 0)
                    await state.update_data(food_name=food_name, calories_per_100g=calories)
                    await message.answer(
                        f"{food_name.capitalize()} — {calories} ккал на 100 г. Сколько грамм вы съели?"
                    )
                    await state.set_state(FoodLoggingState.waiting_for_quantity)
                else:
                    await message.answer("Не удалось найти информацию о продукте.")
            else:
                await message.answer("Ошибка при обращении к API продуктов.")


@dp.message(FoodLoggingState.waiting_for_quantity)
async def process_food_quantity(message: Message, state: FSMContext):
    try:
        grams = float(message.text)
        data = await state.get_data()
        food_name = data["food_name"]
        calories_per_100g = data["calories_per_100g"]

        total_calories = (calories_per_100g / 100) * grams
        user_data = users.get(message.from_user.id)
        user_data["logged_calories"] += total_calories

        await message.answer(
            f"Записано: {food_name.capitalize()} — {total_calories:.1f} ккал ({grams} г)."
        )
        await state.clear()
    except ValueError:
        await message.answer("Введите корректное значение количества (в граммах).")


@dp.message(Command("check_progress"))
async def cmd_check_progress(message: Message):
    user_data = users.get(message.from_user.id)
    if not user_data:
        await message.answer("Сначала настройте профиль с помощью команды /set_profile.")
        return

    progress = (
        f"💧 Прогресс по воде:\n"
        f"- Выпито: {user_data['logged_water']} мл из {user_data['water_goal']} мл.\n"
        f"- Осталось: {max(0, user_data['water_goal'] - user_data['logged_water'])} мл.\n\n"
        f"🍎 Прогресс по калориям:\n"
        f"- Потреблено: {user_data['logged_calories']} ккал из {user_data['calorie_goal']} ккал.\n"
        f"- Сожжено: {user_data['burned_calories']} ккал.\n"
        f"- Баланс: {user_data['logged_calories'] - user_data['burned_calories']} ккал."
    )
    await message.answer(progress)


if __name__ == "__main__":
    import asyncio

    asyncio.run(dp.start_polling(bot))
