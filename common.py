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


class BaseClient:
    def __init__(self, api_key, secret_key, password):
        self.spot = self.connect_exchange(api_key, secret_key, password)

    def fetch_symbol(self, token):
        return token + "/USDT"

    def fetch_spot_balance(self, token):
        return self.spot.fetch_total_balance().get(token, 0)

    def fetch_balance(self, token):
        return self.fetch_spot_balance(token) + self.fetch_earn_balance(token)

    def fetch_price(self, token):
        if token == "USDT":
            return 1
        return self.spot.fetch_ticker(token + "/USDT")["last"]

    def fetch_value(self, token):
        return self.fetch_balance(token) * self.fetch_price(token)

    # 每个交易所必须实现以下方法
    def connect_exchange(self, api_key, secret_key, password):
        raise NotImplementedError

    def trading(self, symbol, side, amount, value):
        raise NotImplementedError

    def fetch_earn_balance(self, token):
        raise NotImplementedError

    def subscribe(self, token, amount):
        raise NotImplementedError

    def redeem(self, token, amount):
        raise NotImplementedError

    def transfer_to_funding(self, reserve):
        raise NotImplementedError


def send_notification(content):
    logger.info(content)
