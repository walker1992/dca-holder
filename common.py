import redis
from loguru import logger
import os
from decimal import Decimal, ROUND_FLOOR
import urllib3
import dotenv

dotenv.load_dotenv()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


Asset = "BTC"


DEFAULT_TYPE = "spot"
BUY = "buy"
SELL = "sell"

EXTRA_AMOUNT = 5
MIN_SPOT_AMOUNT = 5.5

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


class TradeParams:
    def __init__(self, EX):
        SHARES = os.getenv(f"{EX}_SHARES")
        if not SHARES:
            logger.error("请设置SHARES")
        logger.info(f"{EX}_SHARES: {SHARES}")
        MIN_AMOUNT = os.getenv(f"{EX}_MIN_AMOUNT")
        if not MIN_AMOUNT:
            logger.error("请设置MIN_AMOUNT")
        logger.info(f"{EX}_MIN_AMOUNT: {MIN_AMOUNT}")
        MAX_AMOUNT = os.getenv(f"{EX}_MAX_AMOUNT")
        if not MAX_AMOUNT:
            logger.error("请设置MAX_AMOUNT")
        logger.info(f"{EX}_MAX_AMOUNT: {MAX_AMOUNT}")
        MIN_PROFIT_PERCENT = os.getenv(f"{EX}_MIN_PROFIT_PERCENT")
        if not MIN_PROFIT_PERCENT:
            logger.error("请设置MIN_PROFIT_PERCENT")
        logger.info(f"{EX}_MIN_PROFIT_PERCENT: {MIN_PROFIT_PERCENT}")
        ADD_POSITION_RATIO = os.getenv(f"{EX}_ADD_POSITION_RATIO")
        if not ADD_POSITION_RATIO:
            logger.error("请设置ADD_POSITION_RATIO")
        logger.info(f"{EX}_ADD_POSITION_RATIO: {ADD_POSITION_RATIO}")
        INCREASE_POSITION_RATIO = os.getenv(f"{EX}_INCREASE_POSITION_RATIO")
        if not INCREASE_POSITION_RATIO:
            logger.error("请设置INCREASE_POSITION_RATIO")
        logger.info(f"{EX}_INCREASE_POSITION_RATIO: {INCREASE_POSITION_RATIO}")
        try:
            (
                SHARES,
                MIN_AMOUNT,
                MAX_AMOUNT,
                MIN_PROFIT_PERCENT,
                ADD_POSITION_RATIO,
                INCREASE_POSITION_RATIO,
            ) = (
                int(SHARES),
                float(MIN_AMOUNT),
                float(MAX_AMOUNT),
                float(MIN_PROFIT_PERCENT),
                float(ADD_POSITION_RATIO),
                float(INCREASE_POSITION_RATIO),
            )
        except ValueError:
            logger.error("环境变量配置错误")
            raise ValueError("环境变量配置错误")
        self.shares = SHARES
        self.min_amount = MIN_AMOUNT
        self.max_amount = MAX_AMOUNT
        self.min_profit_percent = MIN_PROFIT_PERCENT
        self.add_position_ratio = ADD_POSITION_RATIO
        self.increase_position_ratio = INCREASE_POSITION_RATIO


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

    def transfer_to_funding(self, amount):
        raise NotImplementedError


def round_floor(amount: float):
    return float(Decimal(amount).quantize(Decimal("0.00000001"), rounding=ROUND_FLOOR))


def send_notification(content):
    logger.info(content)
