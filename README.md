<div align="center">
<h1> DCA Holder </h1>


这是一个融合了平均成本法与长期持有策略的加密量化策略, 在主流交易所[币安]上实现, 其思想同样适用于其他核心资产, 如纳指, 黄金等


Github: [https://github.com/gochendong/dca-holder](https://github.com/gochendong/bulita)
</div>

## 特点

1. 只需要填写API即可开启自动化交易, 目前支持币安, 只支持现货BTC/USDT, 支持多账户
2. 程序初始时, 请保证你的现货账户中不持有任何BTC, 并且现货或理财账户中拥有足够的USDT
3. 核心思想是平均成本与屯币, 如果价格上涨, 将在固定盈利点卖出, 并将盈利部分转移至资金账户进行屯币, 如果价格下跌, 将不断补仓, 拉低成本
4. 策略将会利用你现货账户中的USDT和BTC, 以及理财账户中的USDT, 而理财账户中的BTC会被忽略, 以便您手动将资金账户中的BTC转移至理财账户
5. 如果所有资金都买入了BTC导致报错DCA InsufficientFunds, 这时候BTC处于历史低位, 应该从其他地方划转USDT到交易所

## 使用

1. 填写配置文件.env.example, 并将其重命名为.env
2. 确保已运行redis服务
3. 安装依赖 
    ```
    python3 -m pip install -r requirements.txt 
    ```
4. 通过python3 xxx.py启动程序, 程序会自动读取配置文件并开始运行, 可以使用screen/nohup/supervisor等方式实现进程守护

## 参考文献

[https://github.com/ccxt/ccxt](https://github.com/ccxt/ccxt)

[https://binance-docs.github.io/apidocs/spot/cn](https://binance-docs.github.io/apidocs/spot/cn)

## License

[MIT licensed](./LICENSE)
