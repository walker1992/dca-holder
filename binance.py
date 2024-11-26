from common import *
from dca import Trade

EX = "BN"

logger = logger.patch(lambda record: record.update(name=f"[{EX}]"))


SHARES = os.getenv(f"{EX}_SHARES")
if not SHARES:
    logger.error("请设置SHARES")
logger.info(f"SHARES: {SHARES}")
MIN_AMOUNT = os.getenv(f"{EX}_MIN_AMOUNT")
if not MIN_AMOUNT:
    logger.error("请设置MIN_AMOUNT")
logger.info(f"MIN_AMOUNT: {MIN_AMOUNT}")
MAX_AMOUNT = os.getenv(f"{EX}_MAX_AMOUNT")
if not MAX_AMOUNT:
    logger.error("请设置MAX_AMOUNT")
logger.info(f"MAX_AMOUNT: {MAX_AMOUNT}")
MIN_PROFIT_PERCENT = os.getenv(f"{EX}_MIN_PROFIT_PERCENT")
if not MIN_PROFIT_PERCENT:
    logger.error("请设置MIN_PROFIT_PERCENT")
logger.info(f"MIN_PROFIT_PERCENT: {MIN_PROFIT_PERCENT}")
ADD_POSITION_RATIO = os.getenv(f"{EX}_ADD_POSITION_RATIO")
if not ADD_POSITION_RATIO:
    logger.error("请设置ADD_POSITION_RATIO")
logger.info(f"ADD_POSITION_RATIO: {ADD_POSITION_RATIO}")
INCREASE_POSITION_RATIO = os.getenv(f"{EX}_INCREASE_POSITION_RATIO")
if not INCREASE_POSITION_RATIO:
    logger.error("请设置INCREASE_POSITION_RATIO")
logger.info(f"INCREASE_POSITION_RATIO: {INCREASE_POSITION_RATIO}")

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
    logger.error("环境变量格式错误")
    exit(1)


MIN_SUBSCRIBE_BTC_AMOUNT = 0.0015
MIN_SUBSCRIBE_USDT_AMOUNT = 0.1

SUBSCRIBE_LIMIT = {
    "BTC": MIN_SUBSCRIBE_BTC_AMOUNT,
    "USDT": MIN_SUBSCRIBE_USDT_AMOUNT,
}

MIN_REDEEM_BTC_AMOUNT = 0.00001
# MIN_REDEEM_USDT_AMOUNT = 0.001
MIN_REDEEM_USDT_AMOUNT = 1
MIN_REDEEM_BNB_AMOUNT = 0.00001

REDEEM_LIMIT = {
    "BTC": MIN_REDEEM_BTC_AMOUNT,
    "USDT": MIN_REDEEM_USDT_AMOUNT,
}


def init_binance_trade():
    trades = []
    uids, api_keys, secret_keys = (
        os.getenv(f"{EX}_UID"),
        os.getenv(f"{EX}_API_KEY"),
        os.getenv(f"{EX}_SECRET_KEY"),
    )
    if uids and api_keys and secret_keys:
        uids, api_keys, secret_keys = (
            uids.split(","),
            api_keys.split(","),
            secret_keys.split(","),
        )
        if len(uids) != len(api_keys) or len(api_keys) != len(secret_keys):
            logger.error("UID, API_KEY, and SECRET_KEY must have the same length")
            return

        for idx, uid in enumerate(uids):
            client = BinanceClient(api_keys[idx], secret_keys[idx])
            trade = Trade(
                user_id=uid,
                exchange=EX,
                client=client,
                shares=SHARES,
                min_amount=MIN_AMOUNT,
                max_amount=MAX_AMOUNT,
                min_profit_percent=MIN_PROFIT_PERCENT,
                add_position_ratio=ADD_POSITION_RATIO,
                increase_position_ratio=INCREASE_POSITION_RATIO,
            )
            trades.append(trade)

    return trades


class BinanceClient:
    def __init__(self, api_key, api_secret):
        self.spot = self.connect_exchange(api_key, api_secret, DEFAULT_TYPE)

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
                return float(pos["totalAmount"])
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
        logger.info(f"subscribe {amount} {token}")
        try:
            amount = float(decimal.Decimal(amount).quantize(
                Decimal("0.00000001"), rounding=ROUND_FLOOR
            ))
            lower = SUBSCRIBE_LIMIT[token]
            if amount < lower:
                return
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
        amount = float(decimal.Decimal(amount).quantize(
            Decimal("0.00000001"), rounding=ROUND_FLOOR
        ))
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
        time.sleep(5)

    def transfer_to_funding(self, reserve):
        logger.info(f"reserve: {reserve:.8f} {Asset}")
        try:
            self.spot.sapi_post_asset_transfer(
                {
                    "type": "MAIN_FUNDING",
                    "asset": Asset,
                    "amount": reserve,
                    "timestamp": int(time.time() * 1000),
                }
            )
        except Exception as e:
            logger.error(e)

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
