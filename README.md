# 机票价格监控

基于 Playwright 的 Trip.com 网页抓取工具，用于监控往返机票价格并通过 Bark 推送到 iPhone。

**当前版本聚焦**：纯网页抓取（`trip_scrape`），无需任何 API Key。已移除 Google Flights、Kiwi、Amadeus 等付费 API 依赖。

## 环境准备

```bash
conda create -y -n flight-monitor python=3.11
conda activate flight-monitor
pip install -r requirements.txt
python -m playwright install chromium
```

## 核心概念：任务化配置

所有要监控的「出发地 / 目的地 / 日期」都集中在 `config.yaml` 的 `tasks` 列表中。
**新增或调整一次搜索，只需编辑 `config.yaml`，无需改动任何代码或 workflow。**

```yaml
tasks:
  - name: "中秋那霸-香港"        # 任务名（出现在推送标题）
    origin: HKG                  # 出发地 IATA 码
    destination: OKA             # 目的地 IATA 码
    depart_date: "2026-09-24"    # 去程参考日期
    return_date: "2026-09-27"    # 返程参考日期
    window_days: 0              # 去返日期前后滑动窗口天数
    min_trip_days: 3            # 最少行程天数
    no_thailand: true           # true=仅搜 destination；false=同时对比泰国目的地
```

- `no_thailand: false` 时，会同时把 `thailand_destinations` 列表中的城市加入对比。
- 一次 `run-tasks` 会按列表顺序依次执行所有任务。

## 使用方式

### 方式一：GitHub Actions 定时运行（推荐）

工作流 `.github/workflows/nightly-monitor.yml` 在每天凌晨 01:00 (UTC+8) 自动运行：

```bash
python main.py run-tasks
```

它会读取 `config.yaml` 中的全部 `tasks` 并依次执行，结果通过 Bark 推送到 iPhone。

**调整监控目标**：直接编辑 `config.yaml` 的 `tasks` 列表，提交后下次定时运行即生效。
**调整触发时间**：修改 workflow 中的 `cron` 表达式（当前 `0 17 * * *`）。

**所需 GitHub Secrets：**
- `BARK_DEVICE_KEY`: Bark 设备密钥（从 Bark App 获取）。`config.yaml` 中 `bark_device_key` 设为 `null`，运行时由该环境变量注入，避免密钥入库。

### 方式二：本地批量运行

```bash
python main.py run-tasks --config config.yaml
```

### 方式三：手工单次搜索

```bash
python main.py search \
  --origin HKG \
  --destination PQC \
  --depart-date 2026-09-25 \
  --return-date 2026-10-07 \
  --window-days 2 \
  --label "中秋国庆"
```

参数说明：
- `--origin`: 出发地 IATA 码（如 HKG）
- `--destination`: 主目的地 IATA 码（如 PQC）
- `--depart-date` / `--return-date`: 参考去返日期 YYYY-MM-DD
- `--window-days`: 去返日期前后滑动窗口天数（默认 2）
- `--label`: 搜索标签，出现在推送标题中
- `--no-thailand`: 仅搜索指定目的地，不包含泰国目的地
- `--config`: 配置文件路径（默认 config.yaml）

默认行为：同时搜索 `--destination` 和配置文件中 `thailand_destinations` 列表的所有目的地，输出每个目的地的最优价格对比。

### 其他命令

```bash
python main.py init-config --force     # 生成默认配置（tasks 为空）
python main.py run-once --config config.yaml   # 执行一次监控（按 window 配置）
python main.py run --config config.yaml        # 持续循环监控
```

## 配置文件核心字段

```yaml
# 全局设置
provider: trip_scrape          # 数据源（仅支持 trip_scrape / mock）
currency: CNY                   # 输出币种
trip_scrape_timeout_seconds: 60 # 抓取超时
alert_threshold: 2200           # 告警阈值
alert_cooldown_minutes: 180     # 告警冷却
interval_minutes: 30            # 持续监控间隔
notifier: bark                  # 通知方式：bark / console
bark_device_key: null           # 留空，运行时由环境变量 BARK_DEVICE_KEY 注入
thailand_destinations: [BKK]    # 泰国对比目的地（no_thailand=false 时生效）

# 搜索任务列表（GitHub Actions 实际执行的内容）
tasks:
  - name: "中秋那霸-香港"
    origin: HKG
    destination: OKA
    depart_date: "2026-09-24"
    return_date: "2026-09-27"
    window_days: 0
    min_trip_days: 3
    no_thailand: true
```

## 输出示例

```
[中秋那霸-香港] HKG->OKA 2026-09-24/2026-09-27 (3天) go=08:30->10:15 back=19:20->21:05 PRICE=1840.00 CNY direct=Y
```

Bark 推送包含多目的地价格对比内容。

## 功能清单

- **网页抓取**：Playwright 驱动 Trip.com 移动版，两阶段抓取（快速扫价 + 详情补抓）
- **任务化配置**：所有搜索目标集中在 `config.yaml` 的 `tasks` 列表，GitHub Actions 自动批量执行
- **多目的地对比**：同一次搜索同时比 PQC 和泰国多城市
- **滑动窗口**：指定参考日期 ± N 天自动生成往返组合
- **价格位置判定**：基于历史数据标记高位/中位/低位
- **智能告警**：价格低于阈值时自动推送，支持冷却时间
- **Bark 推送**：搜索结果合并推送到 iPhone
- **GitHub Actions**：定时自动化运行，无需本地机器
