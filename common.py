import redis
from loguru import logger
import os
from decimal import Decimal, ROUND_FLOOR
import urllib3
import dotenv
import time
import requests
import message

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
        USE_MULTI_ACCOUNTS = os.getenv(f"{EX}_USE_MULTI_ACCOUNTS")
        if not USE_MULTI_ACCOUNTS:
            logger.error("请设置USE_MULTI_ACCOUNTS")
        logger.info(f"{EX}_USE_MULTI_ACCOUNTS: {USE_MULTI_ACCOUNTS}")
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
                USE_MULTI_ACCOUNTS,
                SHARES,
                MIN_AMOUNT,
                MAX_AMOUNT,
                MIN_PROFIT_PERCENT,
                ADD_POSITION_RATIO,
                INCREASE_POSITION_RATIO,
            ) = (
                bool(USE_MULTI_ACCOUNTS),
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
        self.use_multi_accounts = USE_MULTI_ACCOUNTS
        self.shares = SHARES
        self.min_amount = MIN_AMOUNT
        self.max_amount = MAX_AMOUNT
        self.min_profit_percent = MIN_PROFIT_PERCENT
        self.add_position_ratio = ADD_POSITION_RATIO
        self.increase_position_ratio = INCREASE_POSITION_RATIO


class Trade:
    def __init__(
        self,
        user_id,
        exchange,
        client,
        use_multi_accounts,
        shares,
        min_amount,
        max_amount,
        min_profit_percent,
        add_position_ratio,
        increase_position_ratio,
    ):
        self.user_id = user_id
        self.exchange = exchange.lower()
        self.client = client
        self.use_multi_accounts = use_multi_accounts
        self.shares = shares
        self.min_amount = min_amount
        self.max_amount = max_amount
        self.min_profit_percent = min_profit_percent
        self.add_position_ratio = add_position_ratio
        self.increase_position_ratio = increase_position_ratio


class TokenInfo:
    def __init__(self, token, symbol, balance, price):
        self.token = token
        self.symbol = symbol
        self.balance = balance
        self.price = price


class BaseClient:
    def __init__(self, api_key, secret_key, password, use_multi_accounts):
        self.spot = self.connect_exchange(api_key, secret_key, password)
        self.use_multi_accounts = use_multi_accounts

    def fetch_symbol(self, token):
        return token + "/USDT"

    def fetch_spot_balance(self, token):
        return self.spot.fetch_total_balance().get(token, 0)

    def fetch_balance(self, token):
        if self.use_multi_accounts:
            return self.fetch_spot_balance(token) + self.fetch_earn_balance(token)
        return self.fetch_spot_balance(token)

    def fetch_price(self, token):
        if token == "USDT":
            return 1
        return self.spot.fetch_ticker(token + "/USDT")["last"]

    def fetch_value(self, token):
        return self.fetch_balance(token) * self.fetch_price(token)

    def place_market_order(self, symbol, side, amount, value, reverse):
        logger.info(f"trading {symbol} {side} {amount:.8f} ${value}")
        if reverse:
            amount = amount if side == SELL else value
        order = self.spot.create_market_order(
            symbol=symbol,
            side=side,
            amount=amount,
        )
        while True:
            order = self.spot.fetch_order(order["id"], symbol)
            logger.info(f"order {order}")
            status = order["status"].lower()
            if status == "closed":
                break
            elif status == "canceled":
                return
            elif status == "open":
                continue
            logger.error(f"未知交易状态 {status}")
            time.sleep(1)
        if self.use_multi_accounts:
            self.subscribe("USDT", self.fetch_spot_balance("USDT"))
        cost = order["cost"]
        price = order["average"]
        if cost > 0 and price > 0:
            return {"cost": cost, "price": price}

    # 每个交易所必须实现以下方法
    def connect_exchange(self, api_key, secret_key, password):
        raise NotImplementedError

    # 调用place_market_order方法
    def trading(self, symbol, side, amount, value):
        raise NotImplementedError

    def fetch_earn_balance(self, token):
        raise NotImplementedError

    def subscribe(self, token, amount):
        raise NotImplementedError

    def redeem(self, token, amount):
        raise NotImplementedError

    def transfer_to_funding(self, token, amount):
        raise NotImplementedError


def round_floor(amount: float):
    return float(Decimal(amount).quantize(Decimal("0.00000001"), rounding=ROUND_FLOOR))


# 定义一个函数，发送通知
def notify(content):
    logger.info(content)
    # 发送企业微信消息
    message.send_wechat_message(content)


def calc_pnl(client, token, user_id, ex, min_profit_percent, use_multi_accounts):
    total = client.spot.fetch_balance()["total"]
    balance = total.get(token, 0)
    if balance == 0:
        return
    reserve = 0
    if not use_multi_accounts:
        reserve = rdb.get(f"dca:{user_id}:{ex}:{token}:long:reserve")
        if reserve:
            reserve = float(reserve)
            balance -= reserve
        else:
            reserve = 0
    total_cost = rdb.get(f"dca:{user_id}:{ex}:{token}:long:cost")
    if not total_cost:
        return
    total_cost = float(total_cost)
    price = client.fetch_price(token)
    total_value = balance * price
    reserve_value = reserve * price
    entry_price = total_cost / balance
    target_price = entry_price * (1 + min_profit_percent)
    msg = f"#{user_id}:{ex} entry_price: ${entry_price:.2f} target_price: ${target_price:.2f} total_cost: ${total_cost:.2f} total_value: ${total_value:.2f} pnl: {(total_value - total_cost) / total_cost * 100:.2f}%"
    if not use_multi_accounts:
        msg += f" reserve: ${reserve_value:.2f} {token}"
    logger.info(msg)
