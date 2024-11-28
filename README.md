<div align="center">
<h1> DCA Holder </h1>

这是一个融合了平均成本法与长期持有策略的加密量化策略, 在主流交易所[币安, 欧易, Bitget]上实现, 其思想同样适用于其他核心资产, 如纳指, 黄金等

Github: [https://github.com/gochendong/dca-holder](https://github.com/gochendong/bulita)

<h5>所有代码均有实盘资金不间断测试, 非demo级别, 请放心使用<h5>

有疑问找[布里塔](https://chat.bulita.net)

</div>

## 特点

1. 只需要填写API即可开启自动化交易, 目前支持币安/欧易/Bitget, 只支持现货BTC/USDT, 支持多账户
2. 核心思想是平均成本与屯币, 如果价格上涨, 将在固定盈利点卖出, 并将盈利部分转移至资金账户进行屯币, 如果价格下跌, 将不断补仓, 拉低成本
3. 闲置的USDT会自动划转到理财账户享受借贷利润
4. 如果长期下跌后账户中已经没有足够USDT继续买入BTC, 这时候BTC处于历史低位, 应该从其他地方划转USDT到交易所, 维持程序正常运行

## 使用

1. 填写配置文件.env.example, 并将其重命名为.env
2. 确保已运行redis服务
3. 安装依赖 
    ```
    python3 -m pip install -r requirements.txt 
    ```
4. 运行程序
    ```
    python3 main.py
    ```
   程序会自动读取配置文件并开始运行, 可以使用screen/nohup/supervisor等方式实现进程守护

## 注意事项
1. 程序初始时, 请保证你的现货账户中不持有任何BTC, 并且现货或理财账户中拥有足够的USDT
2. 策略将会利用你现货账户中的USDT和BTC, 以及理财账户中的USDT, 而理财账户中的BTC会被忽略, 您可以手动将资金账户中的BTC转移至理财账户
3. 关闭理财账户的自动申购
4. 程序运行后, 不要手动交易BTC(手动加减仓需停止程序, 并修改redis中dca:xxx:BTC:long:cost对应的值), 充提USDT或交易其他币种不影响策略

## 参考文献

[https://github.com/ccxt/ccxt](https://github.com/ccxt/ccxt)

[https://binance-docs.github.io/apidocs/spot/cn](https://binance-docs.github.io/apidocs/spot/cn)

[https://www.okx.com/docs-v5/zh/](https://www.okx.com/docs-v5/zh/)

[https://www.bitget.com/zh-CN/api-doc/spot/intro](https://www.bitget.com/zh-CN/api-doc/spot/intro)

## License

[MIT licensed](./LICENSE)
