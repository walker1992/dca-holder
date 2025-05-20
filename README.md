# DCA Holder

<div align="center">
这是一个融合了平均成本法与长期持有策略的加密量化策略, 在主流交易所**币安/欧易/Bitget**上实现, 其思想同样适用于其他核心资产, 如纳指, 黄金等

Github: [https://github.com/gochendong/dca-holder](https://github.com/gochendong/bulita)

所有代码均有实盘资金7*24小时测试, 非demo级别, 请放心使用

币安跟单链接: https://www.binance.com/zh-CN/copy-trading/lead-details/4467924166879352065

有疑问找[布里塔](https://chat.bulita.net)
</div>

## 特点

1. 只需要填写API即可开启自动化交易, 目前支持币安/欧易/Bitget, 只支持现货BTC/USDT, 支持多账户
2. **核心思想**是平均成本与屯币, 如果价格上涨, 将在固定盈利点卖出, 并将盈利进行永久屯币, 如果价格下跌, 将不断补仓, 拉低成本
3. 闲置的USDT会自动划转到理财账户享受借贷利润(仅当USE_MULTI_ACCOUNTS为true时)
4. 如果长期下跌后账户中已经没有足够USDT继续买入BTC, 这时候BTC处于历史低位, 应该从其他地方划转USDT到交易所, 维持程序正常运行

## 策略算法详解

### 1. 基础设置
```python
base_amount = float(usdt) / shares  # 基础仓位大小 = 总资金/份数
if min_amount > 0 and base_amount < min_amount:
    base_amount = min_amount
if max_amount > 0 and base_amount > max_amount:
    base_amount = max_amount
```

### 2. 加仓逻辑
```python
multiple = (
    (last_price - price)  # 价格差
    / last_price         # 价格下跌百分比
    // (add_position_ratio + increase_position_ratio * count)  # 基础加仓比例 + 递增加仓比例
)
```
- 当 `multiple >= 1` 时触发加仓，价格跌了一定程度才会加仓
- 加仓金额 = `base_amount`
- 每次加仓后 `count += 1`

### 3. 止盈逻辑
```python
if total_value > total_cost * (1 + min_profit_percent):
    # 触发止盈
```

#### 止盈后的处理
- 如果 `count == 1`（只加仓一次）:
  - 更新价格和成本
- 如果 `count > 1`（多次加仓）:
  - 计算卖出金额 = 当前价值 - 基础仓位
  - 卖出后重置为第一次加仓状态

## 关键参数
- `min_profit_percent`: 最小止盈百分比
- `add_position_ratio`: 基础加仓比例
- `increase_position_ratio`: 递增加仓比例
- `min_amount`/`max_amount`: 最小/最大交易金额
- `shares`: 资金份数

## 特殊处理
- 保留 `reserve` 作为底仓
- 处理灰尘币（价值太小的币）
- 支持多账户模式

## 风险控制
- 最小交易额度检查
- 资金余额检查
- 异常处理（网络错误、限流等）

## 状态记录
使用 Redis 存储以下状态：
- 价格 (`long:price`)
- 成本 (`long:cost`)
- 加仓次数 (`long:count`)
- 底仓 (`long:reserve`)
- USDT 余额 (`usdt:long:balance`)

## 策略特点
1. 动态加仓：根据价格下跌幅度和已加仓次数决定是否加仓
2. 分批止盈：根据加仓次数采用不同的止盈策略
3. 底仓保护：保留一定数量的底仓
4. 资金管理：将资金分成多份，控制每次交易金额
5. 风险控制：设置最小交易额度和最大交易金额

## 使用说明

1. 填写配置文件.env.example, 并将其重命名为.env
2. 确保已运行redis服务
3. 安装依赖 
    ```
    python3 -m pip install -r requirements.txt 
    ```
4. 运行程序
    ```
    python3 main.py
    or
    ./start.sh
    ./stop.sh
    ```
    程序会自动读取配置文件并开始运行, 可以使用screen/nohup/supervisor等方式实现进程守护

## 注意事项
1. 程序初始时, 请保证你的现货账户中不持有任何BTC, 并且现货或理财账户中拥有足够的USDT
2. 如果USE_MULTI_ACCOUNTS为true, 策略将会利用你现货账户中的USDT和BTC, 以及理财账户中的USDT, 并且每次盈利部分都会转移至资金账户
3. 如果USE_MULTI_ACCOUNTS为false, 策略只会使用你现货账户中的USDT和BTC
4. 程序运行后, 不要手动交易BTC(手动加减仓需停止程序, 并修改redis中dca:xxx:BTC:long:cost对应的值), 充提USDT或交易其他币种不影响策略
5. 请确保有足够的资金进行交易
6. 注意设置合理的加仓比例和止盈比例
7. 定期检查策略运行状态
8. 注意处理异常情况

## 作者的话
1. 本策略其实是一种资金管理策略, 逻辑并不复杂, 在风险与利润之间采取了折中的方案, 能永赚的逻辑是基于核心资产的长期升值, 所以对非核心资产无效, 至于什么是核心资产, 根据每个人的认知而不同
2. 很多时候你的资金利用率会比较低, 但同时意味着你的流动资金很充足, 此时你可以充分享受活期理财的稳定收益, 同时以备不时之需
3. 如果长期下跌导致资金被占用, 不用担心, 这说明你已经以较低的平均价买入了大量核心资产, 静待升值即可
4. 长期运行之后, 你会通过低买高卖的价差储备了大量的核心资产

## 参考文献

[https://github.com/ccxt/ccxt](https://github.com/ccxt/ccxt)

[https://binance-docs.github.io/apidocs/spot/cn](https://binance-docs.github.io/apidocs/spot/cn)

[https://www.okx.com/docs-v5/zh/](https://www.okx.com/docs-v5/zh/)

[https://www.bitget.com/zh-CN/api-doc/spot/intro](https://www.bitget.com/zh-CN/api-doc/spot/intro)

## License

[MIT licensed](./LICENSE)

