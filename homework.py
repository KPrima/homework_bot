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
    return all([TELEGRAM_TOKEN, PRACTICUM_TOKEN, TELEGRAM_CHAT_ID])


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
        logging.info(f'Начало запроса. URL: {ENDPOINT}; параметры: {params}')
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
    if not isinstance(response, dict):
        raise TypeError('Ответ API не является словарем')
    if 'homeworks' not in response:
        raise KeyError('Ключ homeworks отсутствует в ответе API')
    if 'current_date' not in response:
        raise KeyError('Ключ current_date отсутствует в ответе API')
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError('homeworks не является списком')
    return homeworks


def parse_status(homework):
    """Извлекает из общей информации статус о конкретной домашней работе."""
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if 'homework_name' not in homework:
        raise KeyError('В ответе API отсутствует ключ homework_name')
    if 'status' not in homework:
        raise KeyError('В ответе API отсутствует ключ status')
    if homework_status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неизвестный статус работы: {homework_status}')
    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}" {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logging.critical('Отсутствуют обязательные переменные окружения')
        sys.exit('Остановка программы в связи с отсутствием обязательной '
                 'переменной окружения'
                 )
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
        handlers=[logging.FileHandler('log.txt'),
                  logging.StreamHandler(sys.stdout)]
    )
    main()
