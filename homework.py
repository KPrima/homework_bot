import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv

from exceptions import ConnectionError, InvalidResponseCode

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}


def check_tokens():
    """Проверяет доступность переменных окружения."""
    values = [
        PRACTICUM_TOKEN,
        TELEGRAM_TOKEN,
        TELEGRAM_CHAT_ID
    ]
    for value in values:
        if value is None:
            logging.critical('Отсутствуют обязательные переменные окружения')
            sys.exit('Остановка программы в связи с отсутствием обязательной '
                     'переменной окружения'
                     )


def send_message(bot, message):
    """Отправляет сообщения в Telegram чат."""
    try:
        logging.info(f'Отправка сообщения {message} начата')
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except telegram.TelegramError as error:
        logging.error(f'Сообщение не отправлено: {error}')
    else:
        logging.debug(f'Сообщение {message} успешно отправлено')


def get_api_answer(timestamp):
    """Отправляет запрос к единственному эндпоинту API-сервиса."""
    timestamp = int(time.time())
    params = {'from_date': timestamp}
    params_request = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': params,
    }
    try:
        response = requests.get(**params_request)
        if response.status_code != HTTPStatus.OK:
            raise InvalidResponseCode(
                'Неверный код ответа. '
                f'Статус: {response.status_code}'
                f'Причина: {response.reason}'
                f'Текст: {response.text}'
            )
        return response.json()
    except Exception:
        raise ConnectionError(
            (
                'Ошибка подключения: URL = {url},'
                'headers = {headers}; '
                'params = {params}'
            ).format(**params_request)
        )


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    logging.debug('Проверка ответа API начата')
    try:
        timestamp = response['current_date']
    except KeyError:
        logging.error('Ключ current_date отсутствует в ответе API')
    try:
        homeworks = response['homeworks']
    except KeyError:
        logging.error('Ключ homeworks отсутствует в ответе API')
    if isinstance(timestamp, int) and isinstance(homeworks, list):
        return homeworks
    else:
        raise TypeError('Неккоректный тип ответа API')


def parse_status(homework):
    """Извлекает из общей информации статус о конкретной домашней работе."""
    homework_name = homework.get('homework_name')
    status = homework.get('status')
    if homework_name is not None and status is not None:
        if status in HOMEWORK_VERDICTS:
            verdict = HOMEWORK_VERDICTS[status]
            return (f'Изменился статус проверки работы "{homework_name}". '
                    f'{verdict}')
        else:
            raise ValueError('Неожиданный статус работы "{homework_name}"')
    else:
        raise ValueError('Отсутствует информация о работе "{homework_name}"')


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                send_message(bot, parse_status(homeworks[0]))
            timestamp = response.get('current_date', timestamp)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message)
            send_message(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s',
        level=logging.DEBUG,
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    main()
