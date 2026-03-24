# Flight Price Monitor (MVP)

用于监控往返机票价格的最小可用版本，默认提供以下测试规则：

- 出发地：广州(CAN)、深圳(SZX)、香港(HKG)
- 目的地：越南富国岛(PQC)
- 日期窗口：自动取当前年份端午节前后 1 天

> 当前版本支持 `trip_scrape` 网页抓取（无需 API Key）、`mock` 演示数据、以及可选 `kiwi` / `amadeus`。

完整操作说明见：`docs/使用文档.md`

## 1) 创建并使用 conda 环境

```bash
conda create -y -n flight-monitor python=3.11
conda activate flight-monitor
pip install -r requirements.txt
python -m playwright install chromium
```

## 2) 生成默认配置

```bash
python main.py init-config
```

会生成 `config.yaml`（默认包含 CAN/SZX/HKG -> PQC + 端午窗口规则）。

## 3) 执行一次监控

```bash
python main.py run-once --config config.yaml
```

快速模式（每个出发地仅抓取一个日期组合）：

```bash
python main.py run-once --config config.yaml --quick
```

## 4) 按周期持续监控

```bash
python main.py run --config config.yaml
```

默认每 30 分钟运行一次，可在 `config.yaml` 中调整。

## 5) 检索同日期泰国最低价

```bash
python main.py run-thailand-cheapest --config config.yaml
```

会基于同一去返日期，扫描 CAN/SZX/HKG 到泰国目的地列表并输出最低价。

## 6) GitHub Actions 定时运行

- 工作流文件：`.github/workflows/nightly-monitor.yml`
- 触发时间：每天北京时间 00:00（GitHub 使用 UTC，对应 `0 16 * * *`）
- 运行命令：`python main.py run-best-deals-summary --config config.yaml`
- 支持手动触发：`workflow_dispatch`

## 配置说明（核心字段）

- `provider`: `trip_scrape` / `mock` / `kiwi` / `amadeus`
- `kiwi_api_key`: 当 `provider=kiwi` 时必填
- `amadeus_client_id` / `amadeus_client_secret`: 当 `provider=amadeus` 时必填
- `amadeus_base_url`: 默认 `https://test.api.amadeus.com`
- `trip_scrape_timeout_seconds`: Trip 网页抓取超时（秒）
- `currency`: 货币代码，如 `CNY`
- `alert_threshold`: 触发告警的价格上限
- `alert_cooldown_minutes`: 同一航线+日期组合告警冷却时间
- `window_start` / `window_end`: 往返日期窗口（系统会生成 `去程 < 返程` 的组合）
- `notifier`: `console` 或 `email`
- `smtp_host`/`smtp_port`/`smtp_username`/`smtp_password`/`smtp_use_tls`: 邮件配置
- `email_from`/`email_to`: 发件人与收件人列表

## 启用 Kiwi 实时查询（示例）

编辑 `config.yaml`：

```yaml
provider: kiwi
kiwi_api_key: "<YOUR_KIWI_API_KEY>"
```

说明：`kiwi` 需要 API Key。若你暂时不想用 Key，可先用下面的免费模式跑通流程。

## 启用 Amadeus 实时查询（免费测试额度）

编辑 `config.yaml`：

```yaml
provider: amadeus
amadeus_client_id: "<YOUR_AMADEUS_CLIENT_ID>"
amadeus_client_secret: "<YOUR_AMADEUS_CLIENT_SECRET>"
amadeus_base_url: https://test.api.amadeus.com
notifier: console
```

可在 Amadeus for Developers 注册测试应用获取 `client_id` 与 `client_secret`，通常有免费测试额度。

## 免费模式（无需 API Key）

```yaml
provider: trip_scrape
notifier: console
```

该模式使用 Playwright 抓取 Trip.com 页面并在控制台输出真实报价。
Trip 抓取原始价格通常为 `USD`，程序会自动按实时汇率换算到你在 `config.yaml` 的 `currency`（例如 `CNY`）。
控制台会输出：起飞时间、到达时间、航班号（若源站未暴露则为 `N/A`）、换算后价格、历史位置（高位/中位/低位）。

如果被反爬导致抓取失败，可临时回退：

```yaml
provider: mock
```

## 启用邮件通知（示例）

编辑 `config.yaml`：

```yaml
notifier: email
smtp_host: smtp.qq.com
smtp_port: 587
smtp_username: your_email@qq.com
smtp_password: your_smtp_auth_code
smtp_use_tls: true
email_from: your_email@qq.com
email_to:
	- receiver1@example.com
```
