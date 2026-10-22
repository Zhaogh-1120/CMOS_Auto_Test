# 原始 ZIP vs 最新 ZIP 文件变更清单

来源：`CMOS_Auto_Test-main(6).zip` → `CMOS_Auto_Test_SPI_Enhanced_Color_20261022.zip`；文件内容逐个比较。

总计：13 个原文件内容变化、10 个新增文件、0 删除文件；ZIP 总条目从 272 增至 282。`full_flow_test` 与 `python_ginkgo_spi` 的修改基本对称。

## 每套子工程：已有文件修改
- `README.md`
- `docs/framework.md`
- `main.py`
- `protocol/chip_spi.py`
- `protocol/register_map.py`
- `tests/write_read_check.py`

此外只有 `full_flow_test/快速上手说明.md` 发生修改（共 6×2+1=13）。

## 每套子工程：新增文件
- `SPI_COMMAND_UPDATE_使用说明.md`
- `SPI_READ_FIX_验证说明.md`
- `tests/read_only_check.py`
- `tests/test_spi_cli_enhancements_mock.py`
- `tests/test_spi_read_protocol_mock.py`

每套 5 个新增文件，共 10 个。

## 没有变化的模块（本次 ZIP 内容对比）
- `driver/control_spi.py` 与 Ginkgo DLL
- `instruments/e5052b/` 及 E5052B 采集模块
- `config/registers.json`、`config/register_fields.json` 等寄存器配置
- 其他旧版测量/扫描脚本（即使它们调用的底层 SPI API 行为会随修复而改变）

注意：这只是在两份用户提供的 ZIP 间对比，不代表 GitHub 当前远端主分支也完全等于最早 ZIP；推送前必须检查远端最新提交与 `git diff`。
