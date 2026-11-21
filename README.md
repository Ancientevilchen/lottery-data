# lottery-data

五个彩种的开奖号码数据，由 GitHub Actions 每天北京时间 22:40 / 23:40 自动抓取并提交。

- `kl8.json` 快乐8
- `ssq.json` 双色球
- `pl5.json` 排列五
- `dlt.json` 大乐透
- `qxc.json` 7星彩

每个文件结构：`{"updated": 最新开奖日期, "latest_issue": 最新期号, "data": [...], "issues": [...], "dates": [...]}`，`data` 首条为最新一期。

已被 doubao 线上页面直接读取。数据源为福彩与体彩官方开奖公告接口，仅作号码记录，不构成任何投注建议。
