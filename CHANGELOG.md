# Changelog — 2026-10-22

## Unreleased: SPI Register Access Enhancement

基于原始 `CMOS_Auto_Test-main(6).zip` 与 `CMOS_Auto_Test_SPI_Enhanced_Color_20261022.zip` 的实际源码比较。发布版本号由仓库维护者决定。

### Fixed
- **SPI 只读协议**：在读取前通过独立 CS 帧发送 Set Address（默认 `0x00, addr`），随后发送 Read Data（`0x80, 0x00`）；有效读回字节为 `raw_rx[1]`。不需要为了选择地址而预先写入配置数据。
- 写入数值和扫描边界在 SPI 写命令之前检查；超出 8-bit REG/Field 位宽的输入会报错，而不是默默截断。

### Added
- 统一读取入口：`read --reg 0x20`、`read --name REG20`、`read --name CFG_OSC2_IDAC_IBIAS`。
- `REGxx`（两位十六进制地址）名称解析，原有 `field-read` 保留。
- REG/Field 写入及扫描统一支持十进制、`0x` 十六进制、`0b` 二进制输入。
- `--dry-run`：读取当前寄存器值并展示预计写入结果，但不发送 Write Data 帧；会发送读取所需的 Set Address 帧。
- `value_hex`、`value_bin=2b...`、`value_dec`，按 HEX → BIN → DEC 顺序输出；REG 二进制按 8-bit 宽度，Field 按字段位宽。
- 对读取名称/值的黄色高亮、命令行错误说明的红色高亮；支持 `NO_COLOR` 环境变量。
- 每套子工程新增 `tests/test_spi_read_protocol_mock.py`、`tests/test_spi_cli_enhancements_mock.py` 和 `tests/read_only_check.py` 等测试/验证资料。

### Changed
- 同步更新 `full_flow_test` 与 `python_ginkgo_spi` 两套程序的 `main.py`、`protocol/chip_spi.py`、`protocol/register_map.py`，以及相关 README / 框架说明。
- 默认 SPI Mode 0（CPOL=0、CPHA=0）和已有 Ginkgo/E5052B 结构保持不变。

### Verified
- 两套子工程各 33 项 mock 测试通过，共 66/66。离线测试不等同于实体 Ginkgo/芯片/E5052B 全流程验证。
- 已有实物验证记录：REG20/REG21 采用两帧读取分别返回过 `0x7C`/`0x79`（具体值取决于芯片当前状态）。

### Known Issues — 尚未修复
1. 回读比较出现 FAIL 时，CLI 仍可能以退出码 0 退出；扫描也可能继续。
2. Field 验证只校验目标字段，其他位异常变化可能遗漏。
3. 未同步的 `--use-shadow` 可能覆盖芯片真实值中的其他位，现阶段避免使用。
4. `batch_write` 存在非法后续条目造成部分写入的风险。
5. SPI 初始化失败后可能未关闭已打开的 USB 设备。
6. 某些 SPI 参数（时钟、CPOL/CPHA/控制模式）尚无完整预检查。
7. 不同扫描工具对非整除终点的处理尚不统一。
8. 部分 FullFlowRecord 在不调用 `finalize_statuses()` 时可能将 SPI FAIL 汇总为 PASS。

不要将上述 Known Issues 描述为本次已修复；不建议在这些问题解决前进行无人值守的长时间自动扫描。
