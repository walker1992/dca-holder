from common import *
from dca import Trade

EX = "BITGET"

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

PRODUCT_ID = {
    "BTC": "928476216922914817",
    "USDT": "964334561256718336",
}


def init_bitget_trade():
    trades = []
    uids, api_keys, secret_keys, passwords = (
        os.getenv(f"{EX}_UID"),
        os.getenv(f"{EX}_API_KEY"),
        os.getenv(f"{EX}_SECRET_KEY"),
        os.getenv(f"{EX}_PASSWORD"),
    )
    if uids and api_keys and secret_keys and passwords:
        uids, api_keys, secret_keys, passwords = (
            uids.split(","),
            api_keys.split(","),
            secret_keys.split(","),
            passwords.split(","),
        )
        if (
            len(uids) != len(api_keys)
            or len(api_keys) != len(secret_keys)
            or len(secret_keys) != len(passwords)
        ):
            logger.error(
                "UID, API_KEY, and SECRET_KEY and PASSWORD must have the same length"
            )
            return

        for idx, uid in enumerate(uids):
            client = BitgetClient(api_keys[idx], secret_keys[idx], passwords[idx])
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


class BitgetClient:
    def __init__(self, api_key, api_secret, password):
        self.spot = self.connect_exchange(api_key, api_secret, password, DEFAULT_TYPE)

    def connect_exchange(self, apiKey, secretKey, password, defaultType):
        return ccxt.bitget(
            {
                "verify": False,
                "enableRateLimit": True,
                "options": {
                    "defaultType": defaultType,
                    "createMarketBuyOrderRequiresPrice": False,
                },
                "password": password,
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
        if token == "BTC":
            return 0
        poss = self.spot.private_earn_get_v2_earn_savings_assets()["data"]["resultList"]
        for pos in poss:
            if pos["productCoin"] == token:
                return float(pos["holdAmount"])
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

            self.spot.private_earn_post_v2_earn_savings_subscribe(
                {
                    "productId": PRODUCT_ID[token],
                    "amount": amount,
                    "periodType": "flexible",
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
        self.spot.private_earn_post_v2_earn_savings_redeem(
            {
                "productId": PRODUCT_ID[token],
                "amount": amount,
                "periodType": "flexible",
            },
        )

    def transfer_to_funding(self, reserve):
        logger.info(f"reserve: {reserve:.8f} {Asset}")
        try:
            self.spot.transfer(
                fromAccount="spot",
                toAccount="p2p",
                code="BTC",
                amount=f"{reserve:.8f}",
            )
        except Exception as e:
            logger.error(e)

    def trading(self, symbol, side, amount, value):
        logger.info(f"trading {symbol} {side} {amount} ${value}")
        order = self.spot.create_market_order(
            symbol=symbol,
            side=side,
            amount=amount if side == SELL else value,
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
