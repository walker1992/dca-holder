from common import *
from dca import Trade

EX = "BN"

MIN_SUBSCRIBE_BTC_AMOUNT = 0.0015
MIN_SUBSCRIBE_USDT_AMOUNT = 0.1

SUBSCRIBE_LIMIT = {
    "BTC": MIN_SUBSCRIBE_BTC_AMOUNT,
    "USDT": MIN_SUBSCRIBE_USDT_AMOUNT,
}

MIN_REDEEM_BTC_AMOUNT = 0.00001
# MIN_REDEEM_USDT_AMOUNT = 0.001
MIN_REDEEM_USDT_AMOUNT = 1

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
            client = BinanceClient(api_keys[idx], secret_keys[idx], "")
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


class BinanceClient(BaseClient):
    def __init__(self, api_key, secret_key, password):
        super().__init__(api_key, secret_key, password)
        self.spot = self.connect_exchange(api_key, secret_key, password)

    def connect_exchange(self, apiKey, secretKey, password):
        return ccxt.binance(
            {
                "verify": False,
                "enableRateLimit": True,
                "options": {
                    "defaultType": DEFAULT_TYPE,
                },
                "apiKey": apiKey,
                "secret": secretKey,
            }
        )

    def fetch_earn_balance(self, token):
        # 理财账户的Asset不计算, 因为申购一般有门槛
        if token == Asset:
            return 0
        poss = self.spot.sapiGetSimpleEarnFlexiblePosition()["rows"]
        for pos in poss:
            if pos["asset"] == token:
                return float(pos["totalAmount"])
        return 0

    def subscribe(self, token, amount):
        logger.info(f"subscribe {amount} {token}")
        try:
            amount = float(
                decimal.Decimal(amount).quantize(
                    Decimal("0.00000001"), rounding=ROUND_FLOOR
                )
            )
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
        amount = float(
            decimal.Decimal(amount).quantize(
                Decimal("0.00000001"), rounding=ROUND_FLOOR
            )
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
