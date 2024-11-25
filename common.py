import redis
from loguru import logger
import os
import decimal
import ccxt
import time
from decimal import Decimal, ROUND_FLOOR
import traceback
import urllib3
import dotenv

dotenv.load_dotenv()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


Asset = "BTC"


DEFAULT_TYPE = "spot"
BUY = "buy"
SELL = "sell"

EXTRA_AMOUNT = 5
MIN_SPOT_AMOUNT = 5

logger = logger.patch(lambda record: record.update(name=f"[DCA-HOLDER]"))


pool = redis.ConnectionPool(
    host=os.getenv("REDIS_HOST"),
    port=os.getenv("REDIS_PORT"),
    password=os.getenv("REDIS_PASSWORD"),
    db=os.getenv("REDIS_DB"),
    decode_responses=True,
)

rdb = redis.StrictRedis(connection_pool=pool)

try:
    rdb.ping()
except redis.exceptions.ConnectionError:
    logger.error("redis连接失败")
    exit(1)


class TokenInfo:
    def __init__(self, token, symbol, balance, price):
        self.token = token
        self.symbol = symbol
        self.balance = balance
        self.price = price


def send_notification(content):
    logger.info(content)
