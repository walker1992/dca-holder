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
if (
    not SHARES
    or not MIN_AMOUNT
    or not MIN_PROFIT_PERCENT
    or not ADD_POSITION_RATIO
    or not INCREASE_POSITION_RATIO
):
    logger.error("请设置环境变量")
    exit(1)

pool = redis.ConnectionPool(
    host=os.getenv("REDIS_HOST"),
    port=os.getenv("REDIS_PORT"),
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
            "BTC"
        ) * trade.fetch_price("BTC")
        rdb.set(f"dca:{user_id}:{EX}:usdt:long:balance", usdt)
    base_amount = max(float(usdt) / int(SHARES), float(MIN_AMOUNT))
    total = trade.spot.fetch_balance()["total"]
    total_value = 0
    total_cost = 0
    dust_token = set()
    holding_token = set()
    TokenList, SymbolList = {}, {}
    if "BTC" not in total:
        price = trade.fetch_price("BTC")
        TokenList["BTC"] = TokenInfo("BTC", "BTC/USDT", 0, price)
        SymbolList["BTC/USDT"] = TokenInfo("BTC", "BTC/USDT", 0, price)
    for token in total:
        if token == "USDT":
            if total["USDT"] < base_amount + EXTRA_AMOUNT:
                trade.redeem("USDT", base_amount + EXTRA_AMOUNT - total["USDT"])
                return
        if token != "BTC":
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
        holding_token.add(token)
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
        TokenList[token] = TokenInfo(token, symbol, balance, price)
        SymbolList[symbol] = TokenInfo(token, symbol, balance, price)

        # 加仓
        multiple = (
            (last_price - price)
            / last_price
            // (float(ADD_POSITION_RATIO) + float(INCREASE_POSITION_RATIO) * count)
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

    last_total_cost = rdb.get(f"dca:{user_id}:{EX}:total_cost")
    if not last_total_cost or round(float(last_total_cost)) != round(total_cost):
        rdb.set(f"dca:{user_id}:bitget:total_cost", total_cost)
        if total_cost and total["BTC"]:
            logger.info(
                f"entry_price: {total_cost / total['BTC']:.2f} total_cost: {total_cost:.2f} total_value:{total_value:.2f} pnl: {(total_value - total_cost) / total_cost * 100:.2f}%"
            )

    # 开仓
    for token in TokenList:
        if token != "BTC":
            continue
        token_info = TokenList[token]
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
    if total_value > total_cost * (1 + float(MIN_PROFIT_PERCENT)):
        logger.info("平仓")
        for token, token_info in TokenList.items():
            if token != "BTC":
                continue
            reserve_btc = (total_value - total_cost) / token_info.price
            logger.info(
                f"btc reserve: ${reserve_btc * token_info.price:.2f} {reserve_btc:.8f} BTC at {token_info.price:.2f}"
            )
            try:
                trade.spot.sapi_post_asset_transfer(
                    {
                        "type": "MAIN_FUNDING",
                        "asset": "BTC",
                        "amount": reserve_btc,
                        "timestamp": int(time.time() * 1000),
                    }
                )
            except Exception as e:
                logger.error(f"{EX}b reserve error: {e}")
            token_info.balance = token_info.balance - reserve_btc
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
        if token == "BTC":
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
        if amount < 0.1:
            return
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
    uids = os.getenv("BN_UID").split(",")
    api_keys = os.getenv("BN_API_KEY").split(",")
    secret_keys = os.getenv("BN_SECRET_KEY").split(",")

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
        except ccxt.errors.NetworkError as e:
            logger.error(f"DCA NetworkError {type(e)}")
        except ccxt.errors.InsufficientFunds:
            logger.warning(f"DCA InsufficientFunds")
            time.sleep(10)
        except Exception as e:
            logger.error(f"dca error {type(e)} {e} {traceback.format_exc()}")
            send_notification(f"dca error {type(e)} {e} {traceback.format_exc()}")


if __name__ == "__main__":
    main()
