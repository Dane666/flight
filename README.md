# Flight Price Monitor (MVP)

用于监控往返机票价格的最小可用版本，默认提供以下测试规则：

- 出发地：广州(CAN)、深圳(SZX)、香港(HKG)
- 目的地：越南富国岛(PQC)
- 日期窗口：自动取当前年份端午节前后 5 天

> 当前版本支持 `trip_scrape` 网页抓取（无需 API Key）、`google_flights`（SerpApi Google Flights）、`mock` 演示数据、以及可选 `kiwi` / `amadeus`。

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

## 5) 检索泰国最低价（按窗口匹配）

```bash
python main.py run-thailand-cheapest --config config.yaml
```

会基于日期窗口内的去返组合，扫描 CAN/SZX/HKG 到泰国目的地列表并输出最低价。
若配置了 `fixed_depart_date/fixed_return_date`，会自动扩展到该日期段前后约 5 天后再匹配。
系统会优先保留“完整覆盖端午假期”的往返组合：可以提前去、延后回，但不会返回未覆盖端午假期的票。

## 6) GitHub Actions 定时运行

- 工作流文件：`.github/workflows/nightly-monitor.yml`
- 触发时间：每天北京时间 00:00（GitHub 使用 UTC，对应 `0 16 * * *`）
- 运行命令：`python main.py run-best-deals-summary --config config.yaml`
- 支持手动触发：`workflow_dispatch`
- 配置来源：优先读取仓库 Secret `MONITOR_CONFIG_YAML` 写入 `config.yaml`，若未配置则自动生成默认配置
- 若希望 GitHub Actions 使用 `google_flights`，建议至少配置仓库 Secret `SERPAPI_API_KEY`
- 可选 Secret：`GOOGLE_FLIGHTS_HL`、`GOOGLE_FLIGHTS_GL`、`FEISHU_WEBHOOK_URL`、`FEISHU_SECRET`

### GitHub Secrets（Google Flights）

若希望仓库里的定时任务默认使用 `google_flights`，在 GitHub 仓库中配置：

- `SERPAPI_API_KEY`: 你的 SerpApi Key
- `GOOGLE_FLIGHTS_HL`: 可选，默认 `en`
- `GOOGLE_FLIGHTS_GL`: 可选，默认 `hk`
- `FEISHU_WEBHOOK_URL`: 可选，飞书机器人 webhook
- `FEISHU_SECRET`: 可选，飞书签名密钥

配置入口：

- GitHub 仓库页面
- `Settings`
- `Secrets and variables`
- `Actions`
- `New repository secret`

## 配置说明（核心字段）

- `provider`: `trip_scrape` / `google_flights` / `mock` / `kiwi` / `amadeus`
- `serpapi_api_key`: 当 `provider=google_flights` 时必填
- `kiwi_api_key`: 当 `provider=kiwi` 时必填
- `amadeus_client_id` / `amadeus_client_secret`: 当 `provider=amadeus` 时必填
- `amadeus_base_url`: 默认 `https://test.api.amadeus.com`
- `google_flights_hl` / `google_flights_gl`: Google Flights 搜索语言与地区参数
- `trip_scrape_timeout_seconds`: Trip 网页抓取超时（秒）
- `currency`: 货币代码，如 `CNY`
- `alert_threshold`: 触发告警的价格上限
- `alert_cooldown_minutes`: 同一航线+日期组合告警冷却时间
- `window_start` / `window_end`: 往返日期窗口（系统会生成 `去程 < 返程` 的组合）
- `min_trip_days`: 最小行程天数（默认 4，避免默认出现 3 天往返）
- `window_start` / `window_end` 与 `min_trip_days` 只是基础约束；系统还会额外要求往返日期完整覆盖端午假期
- `max_trip_span_days`: 去返总跨度上限（默认 6 天，含端午假期）
- `max_leave_workdays`: 除端午假期外允许请假的工作日上限（默认 3 天）
- `notifier`: `console` / `email` / `feishu`
- `smtp_host`/`smtp_port`/`smtp_username`/`smtp_password`/`smtp_use_tls`: 邮件配置
- `email_from`/`email_to`: 发件人与收件人列表
- `feishu_webhook_url`/`feishu_secret`: 飞书机器人 webhook 与可选签名密钥

## 启用 Google Flights（SerpApi）

编辑 `config.yaml`：

```yaml
provider: google_flights
serpapi_api_key: "<YOUR_SERPAPI_KEY>"
google_flights_hl: en
google_flights_gl: hk
notifier: console
```

说明：

- 该模式通过 SerpApi 调用 Google Flights，返回结构化的往返字段。
- 当前实现会优先拿去程最低价候选，再用 `departure_token` 补拿返程详情，因此返程时刻与航班号通常比网页抓取更完整。
- 为保留旧链路，默认配置不会自动切换；你可以在独立配置文件中先验证 `google_flights`，确认满意后再改正式配置。

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
当前 `trip_scrape` 采用“两阶段抓取”：

- 第一阶段：快速扫价格，只做轻量页面解析，尽量缩短全窗口遍历时间
- 第二阶段：只对最终最低价候选补抓详情（时刻、航班号、中转信息）

因此全窗口真实抓取仍会比 `mock` 慢很多，但已经比“所有组合都抓详情”更适合日常使用。

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

## 启用飞书推送（示例）

编辑 `config.yaml`：

```yaml
notifier: feishu
feishu_webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx"
feishu_secret: null
```

说明：

- `feishu_secret` 仅在机器人启用了“签名校验”时填写；否则保持 `null`。
- `run-best-deals-summary` 会按 PQC 与泰国各自独立的最优去返日期输出最低价，并自动将汇总推送到飞书。
