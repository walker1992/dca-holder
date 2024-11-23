import decimal
import os
import threading
import dotenv
import traceback
import ccxt
import time
from loguru import logger
from decimal import Decimal, ROUND_FLOOR
import urllib3
import redis

EX = "bn"
Asset = "BTC"

logger = logger.patch(lambda record: record.update(name=f"[{EX}-spot]"))
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

dotenv.load_dotenv()

SHARES = os.getenv("SHARES")
if not SHARES:
    logger.error("请设置SHARES")
logger.info(f"SHARES: {SHARES}")
MIN_AMOUNT = os.getenv("MIN_AMOUNT")
if not MIN_AMOUNT:
    logger.error("请设置MIN_AMOUNT")
MAX_AMOUNT = os.getenv("MAX_AMOUNT")
if not MAX_AMOUNT:
    logger.error("请设置MAX_AMOUNT")
logger.info(f"MIN_AMOUNT: {MIN_AMOUNT}")
MIN_PROFIT_PERCENT = os.getenv("MIN_PROFIT_PERCENT")
if not MIN_PROFIT_PERCENT:
    logger.error("请设置MIN_PROFIT_PERCENT")
logger.info(f"MIN_PROFIT_PERCENT: {MIN_PROFIT_PERCENT}")
ADD_POSITION_RATIO = os.getenv("ADD_POSITION_RATIO")
if not ADD_POSITION_RATIO:
    logger.error("请设置ADD_POSITION_RATIO")
logger.info(f"ADD_POSITION_RATIO: {ADD_POSITION_RATIO}")
INCREASE_POSITION_RATIO = os.getenv("INCREASE_POSITION_RATIO")
if not INCREASE_POSITION_RATIO:
    logger.error("请设置INCREASE_POSITION_RATIO")
logger.info(f"INCREASE_POSITION_RATIO: {INCREASE_POSITION_RATIO}")

try:
    SHARES, MIN_AMOUNT, MAX_AMOUNT, MIN_PROFIT_PERCENT, ADD_POSITION_RATIO, INCREASE_POSITION_RATIO = int(SHARES), float(MIN_AMOUNT), float(MAX_AMOUNT), float(MIN_PROFIT_PERCENT), float(ADD_POSITION_RATIO), float(INCREASE_POSITION_RATIO)
except ValueError:
    logger.error("环境变量格式错误")
    exit(1)

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

BUY = "buy"
SELL = "sell"

EXTRA_AMOUNT = 5
MIN_SPOT_AMOUNT = 5

MIN_SUBSCRIBE_BTC_AMOUNT = 0.0015
MIN_SUBSCRIBE_USDT_AMOUNT = 0.1
MIN_SUBSCRIBE_BNB_AMOUNT = 0.001

SUBSCRIBE_LIMIT = {
    "BTC": MIN_SUBSCRIBE_BTC_AMOUNT,
    "USDT": MIN_SUBSCRIBE_USDT_AMOUNT,
    "BNB": MIN_SUBSCRIBE_BNB_AMOUNT,
}

MIN_REDEEM_BTC_AMOUNT = 0.00001
# MIN_REDEEM_USDT_AMOUNT = 0.001
MIN_REDEEM_USDT_AMOUNT = 1
MIN_REDEEM_BNB_AMOUNT = 0.00001

REDEEM_LIMIT = {
    "BTC": MIN_REDEEM_BTC_AMOUNT,
    "USDT": MIN_REDEEM_USDT_AMOUNT,
    "BNB": MIN_REDEEM_BNB_AMOUNT,
}


class TokenInfo:
    def __init__(self, token, symbol, balance, price):
        self.token = token
        self.symbol = symbol
        self.balance = balance
        self.price = price


def task(user_id, trade):
    usdt = rdb.get(f"dca:{user_id}:{EX}:usdt:long:balance")
    if not usdt:
        usdt = trade.fetch_balance("USDT") + trade.fetch_balance(
            Asset
        ) * trade.fetch_price(Asset)
        rdb.set(f"dca:{user_id}:{EX}:usdt:long:balance", usdt)
    base_amount = float(usdt) / SHARES
    if MIN_AMOUNT > 0 and base_amount < MIN_AMOUNT:
        base_amount = MIN_AMOUNT
    if MAX_AMOUNT > 0 and base_amount > MAX_AMOUNT:
        base_amount = MAX_AMOUNT
    logger.info(f"base_amount: {base_amount:.2f}")
    if base_amount < MIN_SPOT_AMOUNT:
        logger.info(f"base_amount: {base_amount:.2f} 小于最小交易额度")
        return
    total = trade.spot.fetch_balance()["total"]
    total_value = 0
    total_cost = 0
    # 有些情况下币种会卖不干净, 成为灰尘币
    dust_token = set()
    token_list = {}
    if Asset not in total:
        price = trade.fetch_price(Asset)
        token_list[Asset] = TokenInfo(Asset, f"{Asset}/USDT", 0, price)
    for token in total:
        if token == "USDT":
            if total["USDT"] < base_amount + EXTRA_AMOUNT:
                trade.redeem("USDT", base_amount + EXTRA_AMOUNT - total["USDT"])
                return
        if token != Asset:
            continue
        balance = total[token]
        if balance == 0:
            dust_token.add(token)
            continue
        symbol = token + "/USDT"
        price = trade.fetch_price(token)
        value = balance * price
        if value < EXTRA_AMOUNT:
            dust_token.add(token)
            continue
        total_value += value
        cost = rdb.get(f"dca:{user_id}:{EX}:{token}:long:cost")
        if not cost:
            logger.error(f"no cost for {token}")
            return
        last_price = rdb.get(f"dca:{user_id}:{EX}:{token}:long:price")
        if not last_price:
            logger.error(f"no last_price for {token}")
            return
        count = rdb.get(f"dca:{user_id}:{EX}:{token}:long:count")
        if not count:
            logger.error(f"no count for {token}")
            return
        cost = float(cost)
        total_cost += cost
        last_price = float(last_price)
        count = int(count)
        token_list[token] = TokenInfo(token, symbol, balance, price)

        # 加仓
        multiple = (
            (last_price - price)
            / last_price
            // (ADD_POSITION_RATIO + INCREASE_POSITION_RATIO * count)
        )
        if multiple >= 1:
            logger.info(f"加仓 {token}")
            order = trade.trading(symbol, BUY, base_amount / price, base_amount)
            if order:
                rdb.set(f"dca:{user_id}:{EX}:{token}:long:price", order["price"])
                cost = cost + order["cost"]
                rdb.set(f"dca:{user_id}:{EX}:{token}:long:cost", cost)
                count += 1
                rdb.set(f"dca:{user_id}:{EX}:{token}:long:count", count)
                time.sleep(3)
                return

    # 每次交易后, 重新计算平均成本和最新盈亏
    last_total_cost = rdb.get(f"dca:{user_id}:{EX}:total_cost")
    if not last_total_cost or round(float(last_total_cost)) != round(total_cost):
        rdb.set(f"dca:{user_id}:{EX}:total_cost", total_cost)
        if total_cost and total[Asset]:
            logger.info(
                f"entry_price: {total_cost / total[Asset]:.2f} total_cost: {total_cost:.2f} total_value:{total_value:.2f} pnl: {(total_value - total_cost) / total_cost * 100:.2f}%"
            )

    # 开仓
    for token in token_list:
        if token != Asset:
            continue
        token_info = token_list[token]
        if token not in total or token in dust_token:
            logger.info(f"开仓 {token}")
            rdb.delete(f"dca:{user_id}:{EX}:{token}:long:price")
            rdb.delete(f"dca:{user_id}:{EX}:{token}:long:cost")
            rdb.delete(f"dca:{user_id}:{EX}:{token}:long:count")
            order = trade.trading(
                token_info.symbol, BUY, base_amount / token_info.price, base_amount
            )
            if order:
                rdb.set(f"dca:{user_id}:{EX}:{token}:long:price", order["price"])
                rdb.set(f"dca:{user_id}:{EX}:{token}:long:cost", order["cost"])
                rdb.set(f"dca:{user_id}:{EX}:{token}:long:count", 1)
                time.sleep(3)
                return

    # 平仓
    if total_value > total_cost * (1 + MIN_PROFIT_PERCENT):
        logger.info("平仓")
        for token, token_info in token_list.items():
            if token != Asset:
                continue
            # 将净盈利的Asset转到资金账户
            reserve = (total_value - total_cost) / token_info.price
            logger.info(
                f"reserve: ${reserve * token_info.price:.2f} {reserve:.8f} {Asset} at {token_info.price:.2f}"
            )
            try:
                trade.spot.sapi_post_asset_transfer(
                    {
                        "type": "MAIN_FUNDING",
                        "asset": Asset,
                        "amount": reserve,
                        "timestamp": int(time.time() * 1000),
                    }
                )
            except Exception as e:
                logger.error(f"{EX} reserve error: {e}")
            token_info.balance = token_info.balance - reserve
            count = rdb.get(f"dca:{user_id}:{EX}:{token}:long:count")
            # 加仓后的止盈与没有加仓的止盈方案不一样, 保证尽量少交易, 减少手续费
            if count:
                count = int(count)
                if count == 1:
                    rdb.set(f"dca:{user_id}:{EX}:{token}:long:price", token_info.price)
                    rdb.set(
                        f"dca:{user_id}:{EX}:{token}:long:cost",
                        token_info.balance * token_info.price,
                    )
                else:
                    sell_value = token_info.balance * token_info.price - base_amount
                    sell_amount = sell_value / token_info.price
                    order = trade.trading(
                        token_info.symbol, SELL, sell_amount, sell_value
                    )
                    if order:
                        rdb.set(
                            f"dca:{user_id}:{EX}:{token}:long:price",
                            token_info.price,
                        )
                        rdb.set(f"dca:{user_id}:{EX}:{token}:long:cost", base_amount)
                        rdb.set(f"dca:{user_id}:{EX}:{token}:long:count", 1)

        rdb.delete(f"dca:{user_id}:{EX}:usdt:long:balance")
        time.sleep(3)


def send_notification(content):
    logger.info(content)


class Trade:
    def __init__(self, api_key, api_secret):
        self.spot = self.connect_exchange(api_key, api_secret, "spot")

    def connect_exchange(self, apiKey, secretKey, defaultType):
        return ccxt.binance(
            {
                "verify": False,
                "enableRateLimit": True,
                "options": {
                    "defaultType": defaultType,
                },
                "apiKey": apiKey,
                "secret": secretKey,
            }
        )

    def fetch_symbol(self, token):
        return token + "/USDT"

    def fetch_spot_balance(self, token):
        return self.spot.fetch_total_balance().get(token, 0)

    def fetch_earn_balance(self, token):
        # 理财账户的Asset不计算, 因为申购一般有门槛
        if token == Asset:
            return 0
        poss = self.spot.sapiGetSimpleEarnFlexiblePosition()["rows"]
        for pos in poss:
            if pos["asset"] == token:
                return pos["totalAmount"]
        return 0

    def fetch_balance(self, token):
        return self.fetch_spot_balance(token) + self.fetch_earn_balance(token)

    def fetch_price(self, token):
        if token == "USDT":
            return 1
        return self.spot.fetch_ticker(token + "/USDT")["last"]

    def fetch_value(self, token):
        return self.fetch_balance(token) * self.fetch_price(token)

    def subscribe(self, token, amount):
        try:
            amount = decimal.Decimal(amount).quantize(
                Decimal("0.00000001"), rounding=ROUND_FLOOR
            )
            lower = SUBSCRIBE_LIMIT[token]
            if amount < lower:
                return
            logger.info(f"subscribe {amount} {token}")
            self.spot.sapiPostSimpleEarnFlexibleSubscribe(
                {
                    "productId": token + "001",
                    "amount": amount,
                    "timestamp": int(time.time() * 1000),
                }
            )
        except Exception as e:
            logger.error(e)

    def redeem(self, token, amount):
        logger.info(f"redeem {amount} {token}")
        amount = decimal.Decimal(amount).quantize(
            Decimal("0.00000001"), rounding=ROUND_FLOOR
        )
        lower = REDEEM_LIMIT[token]
        if amount < lower:
            amount = lower
        self.spot.sapiPostSimpleEarnFlexibleRedeem(
            {
                "productId": token + "001",
                "amount": amount,
                "timestamp": int(time.time() * 1000),
            }
        )

    def trading(self, symbol, side, amount, value):
        logger.info(f"trading {symbol} {side} {amount} ${value}")
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
        self.subscribe("USDT", self.fetch_spot_balance("USDT"))
        side_zh = "买入" if order["side"] == BUY else "卖出"
        cost = order["cost"]
        price = order["average"]
        msg = f"[DCA策略] {side_zh} ${cost:.2f} {symbol} at {price:.10f}"
        logger.info(msg)
        # 是否选择发送通知
        # send_notification(msg)
        if cost > 0 and price > 0:
            return {"cost": cost, "price": price}


def main():
    uids, api_keys, secret_keys = (
        os.getenv("BN_UID"),
        os.getenv("BN_API_KEY"),
        os.getenv("BN_SECRET_KEY"),
    )
    if not uids or not api_keys or not secret_keys:
        logger.error("请设置BN_UID, BN_API_KEY, BN_SECRET_KEY")
        return
    uids, api_keys, secret_keys = (
        uids.split(","),
        api_keys.split(","),
        secret_keys.split(","),
    )
    if len(uids) != len(api_keys) != len(secret_keys):
        logger.error("uid, api_key, secret_key not match")
        return

    trades = {}
    for idx, uid in enumerate(uids):
        trade = Trade(api_keys[idx], secret_keys[idx])
        trades[uid] = trade

    threads = []
    for user_id, trader in trades.items():
        thread = threading.Thread(target=dca, args=(user_id, trader))
        threads.append(thread)
        thread.start()


def dca(user_id, trade):
    logger.info(f"dca #{user_id} start")
    rdb.delete(f"dca:{user_id}:{EX}:total_cost")
    while True:
        try:
            task(user_id, trade)
        except ccxt.errors.RateLimitExceeded as e:
            logger.error(f"DCA RateLimitExceeded {type(e)}")
            time.sleep(10)
        except ccxt.errors.InsufficientFunds:
            logger.warning(f"DCA InsufficientFunds")
            time.sleep(10)
        except ccxt.errors.NetworkError as e:
            logger.error(f"DCA NetworkError {type(e)}")
        except ccxt.errors.ExchangeError as e:
            logger.error(f"DCA ExchangeError {str(e)}")
            time.sleep(10)
        except Exception as e:
            logger.error(f"dca error {type(e)} {e} {traceback.format_exc()}")
            send_notification(f"dca error {type(e)} {e} {traceback.format_exc()}")


if __name__ == "__main__":
    main()
