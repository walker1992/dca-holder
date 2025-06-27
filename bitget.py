import os
import time

import ccxt

from common import (
    BaseClient,
    TradeParams,
    Trade,
    round_floor,
    logger,
    Asset,
    DEFAULT_TYPE,
)


EX = "BITGET"

PRODUCT_ID = {
    "USDT": "964334561256718336",
}


def init_bitget_trade():
    trades = []
    uids, api_keys, secret_keys, passwords, use_multi_accounts = (
        os.getenv(f"{EX}_UID"),
        os.getenv(f"{EX}_API_KEY"),
        os.getenv(f"{EX}_SECRET_KEY"),
        os.getenv(f"{EX}_PASSWORD"),
        os.getenv(f"{EX}_USE_MULTI_ACCOUNTS"),
    )
    if not use_multi_accounts:
        logger.error("Please set USE_MULTI_ACCOUNTS")
        return
    use_multi_accounts = use_multi_accounts.lower()
    if use_multi_accounts == "true":
        use_multi_accounts = True
    elif use_multi_accounts == "false":
        use_multi_accounts = False
    else:
        logger.error("USE_MULTI_ACCOUNTS must be true or false")
        return
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
            client = BitgetClient(
                api_keys[idx], secret_keys[idx], passwords[idx], use_multi_accounts
            )
            trade_params = TradeParams(EX)
            trade = Trade(
                user_id=uid,
                exchange=EX,
                client=client,
                use_multi_accounts=use_multi_accounts,
                shares=trade_params.shares,
                min_amount=trade_params.min_amount,
                max_amount=trade_params.max_amount,
                min_profit_percent=trade_params.min_profit_percent,
                add_position_ratio=trade_params.add_position_ratio,
                increase_position_ratio=trade_params.increase_position_ratio,
                profit_mode=trade_params.profit_mode,
            )
            trades.append(trade)
    return trades


class BitgetClient(BaseClient):
    def __init__(self, api_key, secret_key, password, use_multi_accounts):
        super().__init__(api_key, secret_key, password, use_multi_accounts)
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
        if token == Asset:
            return 0
        poss = self.spot.private_earn_get_v2_earn_savings_assets()["data"]["resultList"]
        for pos in poss:
            if pos["productCoin"] == token:
                return float(pos["holdAmount"])
        return 0

    def subscribe(self, token, amount):
        if token == Asset:
            return
        amount = round_floor(amount)
        logger.info(f"subscribe {amount} {token}")
        try:
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
        if token == Asset:
            return
        if amount < 1:
            amount = 1
        amount = round_floor(amount)
        logger.info(f"redeem {amount} {token}")
        self.spot.private_earn_post_v2_earn_savings_redeem(
            {
                "productId": PRODUCT_ID[token],
                "amount": amount,
                "periodType": "flexible",
            },
        )
        time.sleep(10)

    def transfer_to_funding(self, token, amount):
        amount = round_floor(amount)
        logger.info(f"reserve: {amount:.8f} {token}")
        try:
            self.spot.transfer(
                fromAccount="spot", toAccount="p2p", code=token, amount=amount
            )
        except Exception as e:
            logger.error(e)

    def trading(self, symbol, side, amount, value):
        return super().place_market_order(symbol, side, amount, value, True)
