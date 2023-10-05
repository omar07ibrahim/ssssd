# Импортируем необходимые модули
import aiogram
from aiogram import Bot, Dispatcher, types
from aiogram.utils.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.fsm_context import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import requests
import json
import datetime

# Создаем экземпляры бота и диспетчера
bot = Bot(token="6118674154:AAHIJ8QpaVRPoGA7x-PjzT7-SzctgyUG9A4")
dp = Dispatcher(bot, storage=MemoryStorage())

# Создаем класс состояний для конечного автомата
class Payment(StatesGroup):
    amount = State()
    address = State()
    confirmation = State()

# Создаем переменные для хранения настроек и данных
channel_id = "-4034205386"
group_id = "4034205386"
admin_id = "738339858"
wallet_address = "0xfed6A9ff08989C76E6db5342D2844476AFcf333A"
subscription_days = 30 # Срок подписки в днях
min_amount = 0.01 # Минимальная сумма оплаты в ETH
users = {} # Словарь для хранения данных о пользователях

# Создаем функцию для проверки оплаты по адресу и сумме
def check_payment(address, amount):
    # Делаем запрос к API etherscan.io для получения списка транзакций по адресу
    url = f"https://api.etherscan.io/api?module=account&action=txlist&address={address}&startblock=0&endblock=99999999&sort=asc&apikey=5WGEFDTPNCBQ2ETECCY14KHDPZ7BHW53YD"
    response = requests.get(url)
    data = json.loads(response.text)
    # Проверяем, есть ли транзакции по адресу
    if data["status"] == "1" and data["result"]:
        # Перебираем транзакции в обратном порядке (от новых к старым)
        for tx in reversed(data["result"]):
            # Проверяем, что транзакция была успешна и отправлена на наш адрес
            if tx["to"].lower() == address.lower() and tx["isError"] == "0":
                # Конвертируем сумму транзакции из wei в ETH и сравниваем с запрошенной суммой
                tx_amount = int(tx["value"]) / 10**18
                if tx_amount >= amount:
                    # Возвращаем True, если оплата подтверждена
                    return True
    # Возвращаем False, если оплата не подтверждена
    return False

# Создаем функцию для добавления пользователя в группу и канал
async def add_user(user_id):
    # Добавляем пользователя в группу
    await bot.add_chat_member(group_id, user_id)
    # Добавляем пользователя в канал
    await bot.add_chat_member(channel_id, user_id)
    # Сохраняем дату окончания подписки в словаре users
    end_date = datetime.date.today() + datetime.timedelta(days=subscription_days)
    users[user_id] = end_date

# Создаем функцию для удаления пользователя из группы и канала
async def remove_user(user_id):
    # Удаляем пользователя из группы
    await bot.kick_chat_member(group_id, user_id)
    # Удаляем пользователя из канала
    await bot.kick_chat_member(channel_id, user_id)
    # Удаляем пользователя из словаря users
    del users[user_id]

# Создаем функцию для проверки срока подписки всех пользователей и удаления истекших
async def check_subscriptions():
    # Получаем текущую дату
    today = datetime.date.today()
    # Перебираем всех пользователей в словаре users
    for user_id, end_date in users.items():
        # Проверяем, не истек ли срок подписки
        if today > end_date:
            # Удаляем пользователя из группы и канала
            await remove_user(user_id)

# Создаем функцию для отправки сообщения админу с информацией о пользователях
async def send_info():
    # Формируем текст сообщения
    text = "Информация о пользователях:\n\n"
    # Перебираем всех пользователей в словаре users
    for user_id, end_date in users.items():
        # Получаем имя пользователя
        user = await bot.get_chat(user_id)
        user_name = user.full_name
        # Добавляем строку с именем и датой окончания подписки
        text += f"{user_name}: {end_date}\n"
    # Отправляем сообщение админу
    await bot.send_message(admin_id, text)

# Создаем хэндлер для команды /start
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    # Проверяем, является ли пользователь админом
    if message.from_user.id == admin_id:
        # Отправляем приветственное сообщение с командами для администрирования
        await message.answer("Здравствуйте, админ! Вот список доступных команд:\n"
                             "/add - добавить пользователя в группу и канал\n"
                             "/remove - удалить пользователя из группы и канала\n"
                             "/check - проверить срок подписки всех пользователей и удалить истекшие\n"
                             "/info - получить информацию о всех пользователях")
    else:
        # Отправляем приветственное сообщение с предложением оплатить подписку
        await message.answer("Здравствуйте, пользователь! Я бот, который продает доступ к каналу и группе обучения. "
                             "Если вы хотите получить доступ, вам нужно оплатить подписку на 30 дней. "
                             "Стоимость подписки - 0.01 ETH. "
                             "Если вы согласны, нажмите на кнопку 'Оплатить'.")

        # Создаем кнопку для оплаты
        button = types.InlineKeyboardButton("Оплатить", callback_data="pay")
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(button)

        # Отправляем сообщение с кнопкой
        await message.answer("Нажмите на кнопку ниже, чтобы начать процесс оплаты.", reply_markup=keyboard)

# Создаем хэндлер для команды /add (только для админа)
@dp.message_handler(commands=["add"], user_id=admin_id)
async def add(message: types.Message):
    # Отправляем сообщение с просьбой ввести ID пользователя, которого нужно добавить
    await message.answer("Введите ID пользователя, которого нужно добавить в группу и канал.")
    # Переводим конечный автомат в состояние amount
    await Payment.amount.set()

# Создаем хэндлер для состояния amount (только для админа)
@dp.message_handler(state=Payment.amount, user_id=admin_id)
async def process_amount(message: types.Message, state: FSMContext):
    # Получаем ID пользователя из сообщения
    user_id = message.text

    # Проверяем, что ID является целым числом
    try:
        user_id = int(user_id)
    except ValueError:
        # Если нет, отправляем сообщение с ошибкой и возвращаемся в то же состояние
        await message.answer("Неверный формат ID. Пожалуйста, введите целое число.")
        return

    # Проверяем, что пользователь с таким ID существует
    try:
        user = await bot.get_chat(user_id)
    except aiogram.exceptions.BotBlocked:
        # Если нет, отправляем сообщение с ошибкой и возвращаемся в то же состояние
        await message.answer("Пользователь с таким ID не найден или заблокировал бота. Пожалуйста, введите другой ID.")
        return

    # Добавляем пользователя в группу и канал
    await add_user(user_id)
    # Отправляем сообщение с подтверждением добавления
    await message.answer(f"Пользователь {user.full_name} успешно добавлен в группу и канал. Срок подписки истекает {users[user_id]}.")
    # Завершаем конечный автомат
    await state.finish()

# Создаем хэндлер для команды /remove (только для админа)
@dp.message_handler(commands=["remove"], user_id=admin_id)
async def remove(message: types.Message):
    # Отправляем сообщение с просьбой ввести ID пользователя, которого нужно удалить
    await message.answer("Введите ID пользователя, которого нужно удалить из группы и канала.")
    # Переводим конечный автомат в состояние address
    await Payment.address.set()

# Создаем хэндлер для состояния address (только для админа)
@dp.message_handler(state=Payment.address, user_id=admin_id)
async def process_address(message: types.Message, state: FSMContext):
    # Получаем ID пользователя из сообщения
    user_id = message.text

    # Проверяем, что ID является целым числом
    try:
        user_id = int(user_id)
    except ValueError:
        # Если нет, отправляем сообщение с ошибкой и возвращаемся в то же состояние
        await message.answer("Неверный формат ID. Пожалуйста, введите целое число.")
        return

    # Проверяем, что пользователь с таким ID существует и есть в словаре users
    if user_id in users:
        # Удаляем пользователя из группы и канала
        await remove_user(user_id)
        # Отправляем сообщение с подтверждением удаления
        await message.answer(f"Пользователь {user.full_name} успешно удален из группы и канала.")
        # Завершаем конечный автомат
        await state.finish()
    else:
        # Если нет, отправляем сообщение с ошибкой и возвращаемся в то же состояние
        await message.answer("Пользователь с таким ID не найден или не имеет подписки. Пожалуйста, введите другой ID.")
        return
# Создаем хэндлер для команды /check (только для админа)
@dp.message_handler(commands=["check"], user_id=admin_id)
async def check(message: types.Message):
    # Вызываем функцию для проверки срока подписки всех пользователей и удаления истекших
    await check_subscriptions()
    # Отправляем сообщение с подтверждением проверки
    await message.answer("Проверка срока подписки всех пользователей выполнена. Истекшие подписки удалены.")

# Создаем хэндлер для команды /info (только для админа)
@dp.message_handler(commands=["info"], user_id=admin_id)
async def info(message: types.Message):
    # Вызываем функцию для отправки сообщения админу с информацией о пользователях
    await send_info()

# Создаем хэндлер для колбэк-кнопки "Оплатить" (только для обычных пользователей)
@dp.callback_query_handler(lambda c: c.data == "pay", user_id=lambda id: id != admin_id)
async def process_pay(callback_query: types.CallbackQuery):
    # Отправляем уведомление о начале процесса оплаты
    await bot.answer_callback_query(callback_query.id, text="Начинаем процесс оплаты.")
    # Отправляем сообщение с просьбой ввести желаемую сумму оплаты в ETH
    await bot.send_message(callback_query.from_user.id, "Введите желаемую сумму оплаты в ETH. Минимальная сумма - 0.01 ETH.")
    # Переводим конечный автомат в состояние amount
    await Payment.amount.set()

# Создаем хэндлер для состояния amount (только для обычных пользователей)
@dp.message_handler(state=Payment.amount, user_id=lambda id: id != admin_id)
async def process_amount(message: types.Message, state: FSMContext):
    # Получаем сумму оплаты из сообщения
    amount = message.text

    # Проверяем, что сумма является положительным числом
    try:
        amount = float(amount)
        assert amount > 0
    except (ValueError, AssertionError):
        # Если нет, отправляем сообщение с ошибкой и возвращаемся в то же состояние
        await message.answer("Неверный формат суммы. Пожалуйста, введите положительное число.")
        return

    # Проверяем, что сумма не меньше минимальной
    if amount < min_amount:
        # Если да, отправляем сообщение с ошибкой и возвращаемся в то же состояние
        await message.answer(f"Сумма оплаты слишком мала. Минимальная сумма - {min_amount} ETH.")
        return

    # Сохраняем сумму оплаты в конечном автомате
    await state.update_data(amount=amount)

    # Отправляем сообщение с нашим адресом TrustWallet для оплаты
    await message.answer(f"Для оплаты подписки переведите {amount} ETH на наш адрес TrustWallet: {wallet_address}. "
                         "После перевода нажмите на кнопку 'Подтвердить'.")

    # Создаем кнопку для подтверждения оплаты
    button = types.InlineKeyboardButton("Подтвердить", callback_data="confirm")
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(button)

    # Отправляем сообщение с кнопкой
    await message.answer("Нажмите на кнопку ниже, когда выполните перевод.", reply_markup=keyboard)

    # Переводим конечный автомат в состояние confirmation
    await Payment.confirmation.set()
# Создаем хэндлер для колбэк-кнопки "Подтвердить" (только для обычных пользователей)
@dp.callback_query_handler(lambda c: c.data == "confirm", user_id=lambda id: id != admin_id, state=Payment.confirmation)
async def process_confirm(callback_query: types.CallbackQuery, state: FSMContext):
    # Отправляем уведомление о начале проверки оплаты
    await bot.answer_callback_query(callback_query.id, text="Проверяем оплату.")
    # Получаем сумму оплаты из конечного автомата
    data = await state.get_data()
    amount = data.get("amount")
    # Вызываем функцию для проверки оплаты по нашему адресу и сумме
    payment = check_payment(wallet_address, amount)
    # Проверяем, подтверждена ли оплата
    if payment:
        # Если да, добавляем пользователя в группу и канал
        await add_user(callback_query.from_user.id)
        # Отправляем сообщение с подтверждением оплаты и доступом к группе и каналу
        await bot.send_message(callback_query.from_user.id, f"Оплата подтверждена. Вы получили доступ к группе и каналу обучения. Срок подписки истекает {users[callback_query.from_user.id]}.")
        # Завершаем конечный автомат
        await state.finish()
    else:
        # Если нет, отправляем сообщение с ошибкой и возвращаемся в то же состояние
        await bot.send_message(callback_query.from_user.id, "Оплата не подтверждена. Пожалуйста, проверьте свой перевод и нажмите на кнопку 'Подтвердить' еще раз.")
        return


# Создаем хэндлер для обработки новых участников в группе
@dp.chat_member_handler(content_types=types.ChatMemberUpdated)
async def new_member(chat_member: types.ChatMemberUpdated):
    # Получаем ID нового участника
    user_id = chat_member.new_chat_member.user.id
    # Проверяем, что новый участник не бот
    if not chat_member.new_chat_member.user.is_bot:
        # Проверяем, есть ли новый участник в словаре users
        if user_id in users:
            # Если да, отправляем ему приветственное сообщение с датой окончания подписки
            await bot.send_message(user_id, f"Добро пожаловать в группу обучения! Ваша подписка истекает {users[user_id]}.")
        else:
            # Если нет, удаляем его из группы и отправляем ему сообщение с предложением оплатить подписку
            await bot.kick_chat_member(group_id, user_id)
            await bot.send_message(user_id, "Вы не можете присоединиться к этой группе, так как вы не оплатили подписку. Если вы хотите получить доступ, вам нужно оплатить подписку на 30 дней. Стоимость подписки - 0.01 ETH. Для начала процесса оплаты нажмите на кнопку 'Оплатить'.")

            # Создаем кнопку для оплаты
            button = types.InlineKeyboardButton("Оплатить", callback_data="pay")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(button)

            # Отправляем сообщение с кнопкой
            await bot.send_message(user_id, "Нажмите на кнопку ниже, чтобы начать процесс оплаты.", reply_markup=keyboard)

# Создаем хэндлер для обработки новых участников в канале
@dp.chat_member_handler(content_types=types.ChatMemberUpdated)
async def new_member(chat_member: types.ChatMemberUpdated):
    # Получаем ID нового участника
    user_id = chat_member.new_chat_member.user.id
    # Проверяем, что новый участник не бот
    if not chat_member.new_chat_member.user.is_bot:
        # Проверяем, есть ли новый участник в словаре users
        if user_id not in users:
            # Если нет, удаляем его из канала и отправляем ему сообщение с предложением оплатить подписку
            await bot.kick_chat_member(channel_id, user_id)
            await bot.send_message(user_id, "Вы не можете присоединиться к этому каналу, так как вы не оплатили подписку. Если вы хотите получить доступ, вам нужно оплатить подписку на 30 дней. Стоимость подписки - 0.01 ETH. Для начала процесса оплаты нажмите на кнопку 'Оплатить'.")

            # Создаем кнопку для оплаты
            button = types.InlineKeyboardButton("Оплатить", callback_data="pay")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(button)

            # Отправляем сообщение с кнопкой
            await bot.send_message(user_id, "Нажмите на кнопку ниже, чтобы начать процесс оплаты.", reply_markup=keyboard)

# Запускаем бота
if __name__ == "__main__":
    executor.start_polling(dp)
