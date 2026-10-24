# Changelog

本文档记录 CMOS_Auto_Test 工程的主要功能变化。旧版工程、并联谐振打包版与 GitHub `main` 的文件内容均已用于比对；未将仅由缓存、历史实验文件或压缩包整理造成的差异描述为新功能。

## [0.2.0] - 2026-10-24 — Parallel SAW Test Integration

### Added — 并联谐振芯片适配
- 在 `full_flow_test` 中引入并联谐振 SAW 芯片的寄存器映射：REG05–REG14 共 16 个地址、35 个 Field。
- 关键扫描字段：`CFG_OSC_SWCAP` 为 REG05[3:0]；`CFG_OSC_IND_SWCAP_N` 与 `CFG_OSC_IND_SWCAP_P` 分别为 REG06[5:3] 和 REG06[2:0]；`CFG_OSC_IDAC_IBIAS` 为 REG07[4:0]。
- 扫描 IND_CAP 时，同步设置 N/P 两个 Field（P=N），并保留同一寄存器的非目标位。
- 新增并联寄存器映射核查脚本 `parallel_spi_readonly_check.py`；配置表中的默认值仅作为参考，不在 Case 启动时自动写入芯片。

### Added — 自动扫描模板
- `case_saw_pn_sweep_1param.py`：仅扫描 IND_CAP，当前预设 0/2/4/6/7，5 组。
- `case_saw_pn_sweep_2param.py`：IBIAS × IND_CAP，当前预设 IBIAS=0/6/12/15、IND_CAP=0/4/7，12 组。
- `case_saw_pn_sweep_3param.py`：IBIAS × SWCAP × IND_CAP，当前预设 4×4×3=48 组。
- RANGE 扫描支持非整除时补上终点；支持 `--plan`（离线检查）、`--check-point`（单点）及完整扫描运行。
- 运行前读取 REG05–REG14 的真实快照；只扫描指定字段，完成或异常时尝试恢复已写入的寄存器，再读取全部寄存器进行一致性检查。

### Added — 测量报告与分析
- 在保留原有相噪测量、CSV/PNG、单点 Excel 和汇总 Excel 的基础上，新增 `pn_comparison.xlsx`。
- `Overview` 每组数据一行，最后一列嵌入该组的**原始 PNG** 相噪截图；不进行有损 JPEG 转码。
- 新增 `PN_Gallery`、`PN_Overlay`、`Raw_PN`、`Test_Info` 页面；相噪曲线叠加使用采集的真实频偏/相噪数据。
- 保留用于固定参数分析和 Top N 排名的既有汇总报表；新增终端文件链接辅助模块。
- 新增针对并联芯片迁移、相噪对比 Excel 和终端链接的离线测试。

### Preserved — 兼容性
- 保留原有 Ginkgo USB-SPI 两帧式 Set Address / Write Data / Read Data 协议。
- 保留 E5052B 的相噪、载波、Jitter、原始曲线和截图采集接口，以及 `outputs/fullflow/.../run_YYYYMMDD_HHMMSS/` 的保存结构。
- 频率数据按仪器实际返回值保存；**增加 Excel 显示位数不代表仪器达到 1 Hz 测量分辨率**。

### Validation and limitations — 验证与限制
- 提供离线寄存器映射和三套扫描测试；实际 Ginkgo/E5052B 联机表现需在 Windows 实验环境中验证。
- 开启截图时，若仪器截图获取失败，相关 Case 仍可能因截图缺失而失败；不能将离线测试通过解释为截图链路已在所有工作点通过。
- `main.py` 的通用 `field-sweep` 与三套 Case 的“非整除补终点”规则可能不同，使用时以对应命令生成的计划为准。
- 公开发布前请确认寄存器定义、原始 Excel、仪器局域网配置及实验数据是否具有发布权限；不要将 `outputs/`、日志、缓存及未授权设计资料提交到公开仓库。

---

## 历史记录 — 2026-10-22（原工程 SPI Register Access Enhancement）

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
