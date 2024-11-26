import os
import time
import ccxt

from common import (
    BaseClient,
    TradeParams,
    round_down,
    logger,
    Asset,
    DEFAULT_TYPE,
    SELL,
)
from dca import Trade


EX = "BITGET"

MIN_SUBSCRIBE_BTC_AMOUNT = 0.001
MIN_SUBSCRIBE_USDT_AMOUNT = 0.1

SUBSCRIBE_LIMIT = {
    "BTC": MIN_SUBSCRIBE_BTC_AMOUNT,
    "USDT": MIN_SUBSCRIBE_USDT_AMOUNT,
}

MIN_REDEEM_BTC_AMOUNT = 0.00000001
# MIN_REDEEM_USDT_AMOUNT = 0.001
MIN_REDEEM_USDT_AMOUNT = 1

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
            trade_params = TradeParams(EX)
            trade = Trade(
                user_id=uid,
                exchange=EX,
                client=client,
                shares=trade_params.shares,
                min_amount=trade_params.min_amount,
                max_amount=trade_params.max_amount,
                min_profit_percent=trade_params.min_profit_percent,
                add_position_ratio=trade_params.add_position_ratio,
                increase_position_ratio=trade_params.increase_position_ratio,
            )
            trades.append(trade)
    return trades


class BitgetClient(BaseClient):
    def __init__(self, api_key, secret_key, password):
        super().__init__(api_key, secret_key, password)
        self.spot = self.connect_exchange(api_key, secret_key, password)

    def connect_exchange(self, apiKey, secretKey, password):
        return ccxt.bitget(
            {
                "verify": False,
                "enableRateLimit": True,
                "options": {
                    "defaultType": DEFAULT_TYPE,
                    "createMarketBuyOrderRequiresPrice": False,
                },
                "password": password,
                "apiKey": apiKey,
                "secret": secretKey,
            }
        )

    def fetch_earn_balance(self, token):
        # 理财账户的Asset不计算, 因为申购一般有门槛
        if token == "BTC":
            return 0
        poss = self.spot.private_earn_get_v2_earn_savings_assets()["data"]["resultList"]
        for pos in poss:
            if pos["productCoin"] == token:
                return float(pos["holdAmount"])
        return 0

    def subscribe(self, token, amount):
        amount = round_down(amount)
        logger.info(f"subscribe {amount} {token}")
        try:
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
        amount = round_down(amount)
        logger.info(f"redeem {amount} {token}")
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
        time.sleep(5)

    def transfer_to_funding(self, amount):
        amount = round_down(amount)
        logger.info(f"reserve: {amount} {Asset}")
        try:
            self.spot.transfer(
                fromAccount="spot", toAccount="p2p", code=Asset, amount=amount
            )
        except Exception as e:
            logger.error(e)

    def trading(self, symbol, side, amount, value):
        logger.info(f"trading {symbol} {side} {amount:.8f} ${value}")
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
        cost = order["cost"]
        price = order["average"]
        if cost > 0 and price > 0:
            return {"cost": cost, "price": price}
