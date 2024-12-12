import time
import traceback

import ccxt

from common import (
    logger,
    calc_pnl,
    rdb,
    notify,
    Asset,
    TokenInfo,
    MIN_SPOT_AMOUNT,
    EXTRA_AMOUNT,
    BUY,
    SELL,
    Trade,
)


def dca_task(trade: Trade):
    user_id, ex = trade.user_id, trade.exchange
    logger.info(f"#{user_id}:{ex} start")
    calc_pnl(trade.client, Asset, user_id, ex)
    while True:
        try:
            dca_strategy(trade)
        except ccxt.errors.RateLimitExceeded as e:
            logger.error(f"#{user_id}:{ex} DCA RateLimitExceeded {type(e)}")
            time.sleep(10)
        except ccxt.errors.InsufficientFunds:
            logger.warning(f"#{user_id}:{ex} DCA InsufficientFunds")
            time.sleep(10)
        except ccxt.errors.RequestTimeout as e:
            pass
        except ccxt.errors.NetworkError as e:
            logger.error(f"#{user_id}:{ex} DCA NetworkError {type(e)}")
        except ccxt.errors.ExchangeError as e:
            logger.error(f"#{user_id}:{ex} DCA ExchangeError {str(e)}")
            time.sleep(10)
        except Exception as e:
            logger.error(f"#{user_id}:{ex} {type(e)} {e} {traceback.format_exc()}")
            notify(f"dca:{user_id}:{ex} {type(e)} {e} {traceback.format_exc()}")


def dca_strategy(trade: Trade):
    user_id = trade.user_id
    ex = trade.exchange
    client = trade.client
    shares = trade.shares
    min_amount = trade.min_amount
    max_amount = trade.max_amount
    min_profit_percent = trade.min_profit_percent
    add_position_ratio = trade.add_position_ratio
    increase_position_ratio = trade.increase_position_ratio

    usdt = rdb.get(f"dca:{user_id}:{ex}:usdt:long:balance")
    if not usdt:
        usdt = client.fetch_balance("USDT") + client.fetch_balance(
            Asset
        ) * client.fetch_price(Asset)
        rdb.set(f"dca:{user_id}:{ex}:usdt:long:balance", usdt)
    base_amount = float(usdt) / shares
    if min_amount > 0 and base_amount < min_amount:
        base_amount = min_amount
    if max_amount > 0 and base_amount > max_amount:
        base_amount = max_amount
    if base_amount < MIN_SPOT_AMOUNT:
        logger.info(f"#{user_id}:{ex} base_amount: {base_amount:.2f} 小于最小交易额度")
        return
    total = client.spot.fetch_balance()["total"]
    total_value = 0
    total_cost = 0
    # 有些情况下币种会卖不干净, 成为灰尘币
    dust_token = set()
    token_list = {}
    if total.get("USDT", 0) < base_amount + EXTRA_AMOUNT:
        client.redeem("USDT", base_amount + EXTRA_AMOUNT - total.get("USDT", 0))
        return
    for token in [Asset]:
        balance = total.get(token, 0)
        if balance == 0:
            dust_token.add(token)
            continue
        symbol = token + "/USDT"
        price = client.fetch_price(token)
        value = balance * price
        if value < EXTRA_AMOUNT:
            dust_token.add(token)
            continue
        total_value += value
        cost = rdb.get(f"dca:{user_id}:{ex}:{token}:long:cost")
        if not cost:
            logger.error(f"#{user_id}:{ex} no cost for {token}")
            return
        last_price = rdb.get(f"dca:{user_id}:{ex}:{token}:long:price")
        if not last_price:
            logger.error(f"#{user_id}:{ex} no last_price for {token}")
            return
        count = rdb.get(f"dca:{user_id}:{ex}:{token}:long:count")
        if not count:
            logger.error(f"#{user_id}:{ex} no count for {token}")
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
            // (add_position_ratio + increase_position_ratio * count)
        )
        if multiple >= 1:
            logger.info(f"#{user_id}:{ex} 加仓 {token}")
            order = client.trading(symbol, BUY, base_amount / price, base_amount)
            if order:
                rdb.set(f"dca:{user_id}:{ex}:{token}:long:price", order["price"])
                cost = cost + order["cost"]
                rdb.set(f"dca:{user_id}:{ex}:{token}:long:cost", cost)
                count += 1
                rdb.set(f"dca:{user_id}:{ex}:{token}:long:count", count)
                time.sleep(5)
                msg = f"#{user_id}:{ex} {BUY} ${order['cost']:.2f} {symbol} at {order['price']:.2f}"
                notify(msg)
                calc_pnl(client, Asset, user_id, ex)
                return

    if Asset not in token_list:
        price = client.fetch_price(Asset)
        token_list[Asset] = TokenInfo(Asset, f"{Asset}/USDT", 0, price)

    # 开仓
    for token in token_list:
        if token != Asset:
            continue
        token_info = token_list[token]
        if token not in total or token in dust_token:
            logger.info(f"#{user_id}:{ex} 开仓 {token}")
            rdb.delete(f"dca:{user_id}:{ex}:{token}:long:price")
            rdb.delete(f"dca:{user_id}:{ex}:{token}:long:cost")
            rdb.delete(f"dca:{user_id}:{ex}:{token}:long:count")
            order = client.trading(
                token_info.symbol, BUY, base_amount / token_info.price, base_amount
            )
            if order:
                rdb.set(f"dca:{user_id}:{ex}:{token}:long:price", order["price"])
                rdb.set(f"dca:{user_id}:{ex}:{token}:long:cost", order["cost"])
                rdb.set(f"dca:{user_id}:{ex}:{token}:long:count", 1)
                time.sleep(5)
                msg = f"#{user_id}:{ex} {BUY} ${order['cost']:.2f} {token_info.symbol} at {order['price']:.2f}"
                notify(msg)
                calc_pnl(client, Asset, user_id, ex)
                return

    # 平仓
    if total_value > total_cost * (1 + min_profit_percent):
        logger.info(f"#{user_id}:{ex} 平仓")
        for token, token_info in token_list.items():
            if token != Asset:
                continue
            # 将净盈利的Asset转到资金账户
            reserve = (total_value - total_cost) / token_info.price
            client.transfer_to_funding(token, reserve)

            token_info.balance = token_info.balance - reserve
            count = rdb.get(f"dca:{user_id}:{ex}:{token}:long:count")
            # 加仓后的止盈与没有加仓的止盈方案不一样, 保证尽量少交易, 减少手续费
            if count:
                count = int(count)
                if count == 1:
                    rdb.set(f"dca:{user_id}:{ex}:{token}:long:price", token_info.price)
                    rdb.set(
                        f"dca:{user_id}:{ex}:{token}:long:cost",
                        token_info.balance * token_info.price,
                    )
                else:
                    sell_value = token_info.balance * token_info.price - base_amount
                    sell_amount = sell_value / token_info.price
                    order = client.trading(
                        token_info.symbol, SELL, sell_amount, sell_value
                    )
                    if order:
                        rdb.set(
                            f"dca:{user_id}:{ex}:{token}:long:price",
                            token_info.price,
                        )
                        rdb.set(f"dca:{user_id}:{ex}:{token}:long:cost", base_amount)
                        rdb.set(f"dca:{user_id}:{ex}:{token}:long:count", 1)
                        msg = f"#{user_id}:{ex} {SELL} ${order['cost']:.2f} {token_info.symbol} at {order['price']:.2f}"
                        notify(msg)

        rdb.delete(f"dca:{user_id}:{ex}:usdt:long:balance")
        time.sleep(5)
        calc_pnl(client, Asset, user_id, ex)
