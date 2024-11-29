import os
import time
import ccxt
from functools import partial

from common import BaseClient, TradeParams, round_floor, logger, Asset, DEFAULT_TYPE
from dca import Trade


EX = "BN"


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
        if token == Asset:
            return 0
        poss = self.spot.sapiGetSimpleEarnFlexiblePosition()["rows"]
        for pos in poss:
            if pos["asset"] == token:
                return float(pos["totalAmount"])
        return 0

    def subscribe(self, token, amount):
        if token == Asset:
            return
        amount = round_floor(amount)
        logger.info(f"subscribe {amount} {token}")
        try:
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
        if token == Asset:
            return
        if amount < 1:
            amount = 1
        amount = round_floor(amount)
        logger.info(f"redeem {amount} {token}")
        self.spot.sapiPostSimpleEarnFlexibleRedeem(
            {
                "productId": token + "001",
                "amount": amount,
                "timestamp": int(time.time() * 1000),
            }
        )
        time.sleep(5)

    def transfer_to_funding(self, token, reserve):
        logger.info(f"reserve: {reserve:.8f} {Asset}")
        try:
            self.spot.sapi_post_asset_transfer(
                {
                    "type": "MAIN_FUNDING",
                    "asset": token,
                    "amount": reserve,
                    "timestamp": int(time.time() * 1000),
                }
            )
        except Exception as e:
            logger.error(e)

    def trading(self, symbol, side, amount, value):
        partial(super().place_market_order, reverse=False)
