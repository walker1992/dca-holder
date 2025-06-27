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

# OKX交易所标识符
EX = "OKX"


def init_okx_trade():
    """
    初始化OKX交易实例
    
    从环境变量中读取多个账户的配置信息，创建对应的交易实例
    支持多账户交易，每个账户需要提供UID、API密钥、密钥密码等信息
    
    Returns:
        list: 包含所有交易实例的列表，如果配置错误则返回None
    """
    trades = []
    
    # 从环境变量获取OKX配置信息
    # 支持多账户，用逗号分隔多个值
    uids, api_keys, secret_keys, passwords, use_multi_accounts = (
        os.getenv(f"{EX}_UID"),           # 用户ID列表
        os.getenv(f"{EX}_API_KEY"),      # API密钥列表
        os.getenv(f"{EX}_SECRET_KEY"),   # 密钥密码列表
        os.getenv(f"{EX}_PASSWORD"),     # 交易密码列表
        os.getenv(f"{EX}_USE_MULTI_ACCOUNTS"),  # 是否启用多账户
    )
    
    # 检查是否启用多账户配置
    if not use_multi_accounts:
        logger.error("Please set USE_MULTI_ACCOUNTS")
        return
    
    # 解析多账户配置标志
    use_multi_accounts = use_multi_accounts.lower()
    if use_multi_accounts == "true":
        use_multi_accounts = True
    elif use_multi_accounts == "false":
        use_multi_accounts = False
    else:
        logger.error("USE_MULTI_ACCOUNTS must be true or false")
        return
    
    # 验证所有必需的配置项都已提供
    if uids and api_keys and secret_keys and passwords:
        # 将逗号分隔的字符串拆分为列表
        uids, api_keys, secret_keys, passwords = (
            uids.split(","),
            api_keys.split(","),
            secret_keys.split(","),
            passwords.split(","),
        )
        
        # 验证所有配置列表长度一致
        if (
            len(uids) != len(api_keys)
            or len(api_keys) != len(secret_keys)
            or len(secret_keys) != len(passwords)
        ):
            logger.error(
                "UID, API_KEY, and SECRET_KEY and PASSWORD must have the same length"
            )
            return
        
        # 为每个账户创建交易实例
        for idx, uid in enumerate(uids):
            # 创建OKX客户端
            client = OKXClient(
                api_keys[idx], secret_keys[idx], passwords[idx], use_multi_accounts
            )
            # 获取交易参数配置
            trade_params = TradeParams(EX)
            # 创建交易实例
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


class OKXClient(BaseClient):
    """
    OKX交易所客户端
    
    继承自BaseClient，实现OKX特有的API交互功能
    主要功能包括：现货交易、理财产品操作、账户间资金转移等
    """
    
    def __init__(self, api_key, secret_key, password, use_multi_accounts):
        """
        初始化OKX客户端
        
        Args:
            api_key (str): OKX API密钥
            secret_key (str): OKX密钥密码
            password (str): OKX交易密码
            use_multi_accounts (bool): 是否启用多账户模式
        """
        super().__init__(api_key, secret_key, password, use_multi_accounts)
        # 创建现货交易连接
        self.spot = self.connect_exchange(api_key, secret_key, password)

    def connect_exchange(self, apiKey, secretKey, password):
        """
        连接OKX交易所
        
        使用ccxt库创建OKX交易所连接实例
        配置包括SSL验证、限流、默认交易类型等
        
        Args:
            apiKey (str): API密钥
            secretKey (str): 密钥密码
            password (str): 交易密码
            
        Returns:
            ccxt.okx: OKX交易所连接实例
        """
        return ccxt.okx(
            {
                "verify": False,              # 禁用SSL证书验证
                "enableRateLimit": True,      # 启用API限流保护
                "options": {
                    "defaultType": DEFAULT_TYPE,  # 设置默认交易类型（现货/期货等）
                },
                "apiKey": apiKey,
                "secret": secretKey,
                "password": password,         # OKX需要交易密码
            }
        )

    def fetch_earn_balance(self, token):
        """
        获取理财产品余额
        
        调用OKX理财账户API获取指定代币的理财余额
        
        Args:
            token (str): 代币符号（如USDT、BTC等）
            
        Returns:
            float: 理财产品中的代币余额，如果是基础资产或未找到则返回0
        """
        # 如果是基础资产，直接返回0
        if token == Asset:
            return 0
        
        # 调用OKX API: GET /api/v5/finance/savings/balance
        # 获取理财账户余额信息
        poss = self.spot.private_get_finance_savings_balance()["data"]
        
        # 遍历所有理财产品，查找指定代币
        for pos in poss:
            if pos["ccy"] == token:  # ccy: currency 货币代码
                return float(pos["amt"])  # amt: amount 金额
        return 0

    def subscribe(self, token, amount):
        """
        申购理财产品
        
        将指定数量的代币从交易账户转移到资金账户，然后申购理财产品
        
        Args:
            token (str): 代币符号
            amount (float): 申购金额
        """
        # 如果是基础资产，跳过申购
        if token == Asset:
            return
        
        # 金额向下取整到合适精度
        amount = round_floor(amount)
        logger.info(f"subscribe {amount} {token}")
        
        try:
            # 步骤1: 将资金从交易账户转移到资金账户
            self.transfer_to_funding(token, amount)
            
            # 步骤2: 调用OKX API申购理财产品
            # POST /api/v5/finance/savings/purchase-redempt
            self.spot.private_post_finance_savings_purchase_redempt(
                {
                    "ccy": token,           # 货币代码
                    "amt": float(amount),   # 申购金额
                    "side": "purchase",     # 操作类型：申购
                    "rate": 0.01,          # 利率（可能是最低接受利率）
                }
            )
        except Exception as e:
            logger.error(e)

    def redeem(self, token, amount):
        """
        赎回理财产品
        
        从理财产品中赎回指定数量的代币，并转移到现货交易账户
        
        Args:
            token (str): 代币符号
            amount (float): 赎回金额
        """
        # 如果是基础资产，跳过赎回
        if token == Asset:
            return
        
        # 确保赎回金额至少为1
        if amount < 1:
            amount = 1
        
        # 金额向下取整
        amount = round_floor(amount)
        logger.info(f"redeem {amount} {token}")
        
        # 步骤1: 调用OKX API赎回理财产品
        # POST /api/v5/finance/savings/purchase-redempt
        self.spot.private_post_finance_savings_purchase_redempt(
            {
                "ccy": token,           # 货币代码
                "amt": float(amount),   # 赎回金额
                "side": "redempt",      # 操作类型：赎回
                "rate": 0.01,          # 利率参数
            }
        )
        
        # 等待赎回处理完成
        time.sleep(5)
        
        # 步骤2: 将赎回的资金从资金账户转移到现货交易账户
        self.transfer_to_spot(token, amount)
        
        # 等待转账完成
        time.sleep(5)

    def trading(self, symbol, side, amount, value):
        """
        执行现货交易
        
        调用父类的市价单交易方法
        
        Args:
            symbol (str): 交易对符号（如BTC-USDT）
            side (str): 交易方向（buy/sell）
            amount (float): 交易数量
            value (float): 交易金额
            
        Returns:
            交易结果
        """
        return super().place_market_order(symbol, side, amount, value, False)

    def transfer_to_spot(self, token, amount):
        """
        转账到现货交易账户
        
        将资金从资金账户（账户类型6）转移到交易账户（账户类型18）
        
        Args:
            token (str): 代币符号
            amount (float): 转账金额
        """
        try:
            # OKX账户类型说明：
            # 6：资金账户（Funding Account）- 用于理财、借贷等
            # 18：交易账户（Trading Account）- 用于现货交易
            self.spot.transfer(token, amount, "6", "18")
        except Exception as e:
            logger.error(e)

    def transfer_to_funding(self, token, amount):
        """
        转账到资金账户
        
        将资金从交易账户（账户类型18）转移到资金账户（账户类型6）
        用于理财产品申购前的资金准备
        
        Args:
            token (str): 代币符号
            amount (float): 转账金额
        """
        # 如果是基础资产，对金额进行向下取整
        if token == Asset:
            amount = round_floor(amount)
        
        try:
            # 从交易账户转移到资金账户
            self.spot.transfer(token, amount, "18", "6")
        except Exception as e:
            logger.error(e)
