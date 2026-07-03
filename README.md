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

## 快速上手

### 1. 手工搜索（推荐）

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

### 2. 生成配置

```bash
python main.py init-config --force
```

### 3. 持续监控

```bash
python main.py run-once --config config.yaml
python main.py run --config config.yaml
```

## GitHub Actions 定时运行

工作流文件 `.github/workflows/nightly-monitor.yml` 自动执行以下搜索：

| 节日 | 日期范围 | 说明 |
|------|---------|------|
| 中秋 | 09-24 ~ 09-27 | 中秋节前后一天 |
| 国庆 | 10-01 ~ 10-07 | 国庆假期前后一天 |
| 中秋国庆桥 | 09-24 ~ 10-07 | 请假 3 天连休方案 |
| 春节 | 02-14 ~ 02-22 | 春节前后两天 |
| 春节特价 | 02-07 ~ 02-10 | 节前特价窗口 |

每次搜索同时对比 PQC 和泰国多目的地最低价，结果通过 Bark 推送到 iPhone。

**所需 GitHub Secrets：**
- `BARK_DEVICE_KEY`: Bark 设备密钥（从 Bark App 获取）

## 配置文件核心字段

```yaml
provider: trip_scrape          # 数据源（仅支持 trip_scrape）
currency: CNY                   # 输出币种
trip_scrape_timeout_seconds: 60 # 抓取超时
alert_threshold: 2200           # 告警阈值
alert_cooldown_minutes: 180     # 告警冷却
interval_minutes: 30            # 持续监控间隔
origins: [HKG]                  # 出发地
destination: PQC                # 主目的地
thailand_destinations: [BKK]    # 泰国对比目的地
bark_device_key: "..."          # Bark 设备密钥
notifier: bark                  # 通知方式：bark / console
```

## 输出示例

```
[中秋] HKG->PQC 2026-09-24/2026-09-28 (4天) go=08:30->10:15 back=19:20->21:05 PRICE=1840.00 CNY (src=266.00 USD) flight=CX123 airline=Cathay Pacific direct=Y
[中秋] HKG->BKK 2026-09-25/2026-09-29 (4天) go=09:15->11:30 back=17:45->20:10 PRICE=2100.00 CNY (src=304.00 USD) flight=TG601 airline=Thai Airways direct=Y
```

Bark 推送包含多目的地价格对比内容。

## 功能清单

- **网页抓取**：Playwright 驱动 Trip.com 移动版，两阶段抓取（快速扫价 + 详情补抓）
- **多目的地对比**：同一次搜索同时比 PQC 和泰国多城市
- **滑动窗口**：指定参考日期 ± N 天自动生成往返组合
- **价格位置判定**：基于历史数据标记高位/中位/低位
- **智能告警**：价格低于阈值时自动推送，支持冷却时间
- **Bark 推送**：多节日搜索结果合并推送到 iPhone
- **GitHub Actions**：定时自动化运行，无需本地机器
