# 并联谐振 SAW 芯片测试工程迁移说明

本工程以用户提供的 `CMOS_Auto_Test-0.2.0(3).zip` 为基础，保留原有 Ginkgo 驱动、SPI 时序、E5052B SCPI/采集/积分/导出实现、既有 `full_flow_test` 文件组织及输出目录层级。**本说明中的 PASS 为离线模拟结论，尚未在用户的 Ginkgo 或 E5052B 实机上验证。**

## 1. 新芯片的寄存器定义

来源：`docs/register_map_parallel/TO202605_UWBSAW_REGLIST_NEW.xlsx`，Sheet1。

- 16 个合法寄存器：`REG05–REG14`（包括两端）；35 个可命名 Field。
- `CFG_OSC_SWCAP<3:0>`：`REG05[3:0]`，0–15。
- `CFG_OSC_IND_SWCAP_N<5:3>`：`REG06[5:3]`，0–7。
- `CFG_OSC_IND_SWCAP_P<2:0>`：`REG06[2:0]`，0–7。
- `CFG_OSC_IDAC_IBIAS<4:0>`：`REG07[4:0]`，0–31。
- 扫描 IND_CAP 时 `P=N`，对 REG06 完整单字节只写一次，保留高两位。
- Excel 内的十进制/十六进制值为**参考默认配置，不进行任何启动时默认初始化写入**。对于实际芯片，始终优先读取实时寄存器内容。

四份 `register_fields.json` 以及四份 `registers.json` 已一起替换，避免默认 `ChipSpi()->RegisterMap()` 路径和 `config/active/` 路径不一致。SPI 参数与 `config/instrument/e5052b_config.json` 原样保留。

## 2. 当前支持的测试模板

| 文件 | 扫描字段 | 写入 REG | 组合数 | 初始/最终快照 |
|---|---|---|---:|---|
| `case_saw_pn_sweep_1param.py` | IND_CAP = [0,2,4,6,7] | REG06 | 5 | REG05–REG14 |
| `case_saw_pn_sweep_2param.py` | IBIAS = [0,6,12,15] × IND_CAP = [0,4,7] | REG07/REG06 | 12 | REG05–REG14 |
| `case_saw_pn_sweep_3param.py` | IBIAS = [0,15,30,31] × SWCAP = [0,7,14,15] × IND_CAP = [0,4,7] | REG07/REG05/REG06 | 48 | REG05–REG14 |

上述范围用于保留既有模板，**不是新芯片最终的测试计划**。正式扫描前应先检查新的寄存器功能、供电和起振状态。每个模板保持“先对本组目标 REG 写入/回读，再一次 E5052B 相噪采集”的顺序，所有 RANGE 仍包含终点。

1/2Param 的未扫描字段沿用芯片现场读回值，不写入默认码。三套 Case 结束时只恢复实际发生过写入的 REG，随后再次读取全部 16 个寄存器，生成 JSON 和 Excel 对比报告。

## 3. 下一步推荐的验证顺序（在 VS Code，进入 full_flow_test）

```bat
:: A. 完全离线，确认读入 35 个 Field 与 16 个寄存器
python -m scripts.fullflow.parallel_spi_readonly_check

:: B. 完全离线，确认三套扫描计划；不打开 Ginkgo 或 E5052B
python -m scripts.fullflow.case_saw_pn_sweep_1param --plan
python -m scripts.fullflow.case_saw_pn_sweep_2param --plan
python -m scripts.fullflow.case_saw_pn_sweep_3param --plan

:: C. 离线模拟回归；包含写入作用范围、全量快照和 Excel 报告
python -m unittest tests.test_parallel_migration_offline -v

:: D. 真实 Ginkgo：只读 REG05–REG14，不执行任何寄存器数据写入
python -m scripts.fullflow.parallel_spi_readonly_check --read

:: E. 真实 E5052B：原工程的独立单次采集流程，无 SPI 动作
python -m scripts.fullflow.e5052b_capture_once

:: F. 前两项硬件验证均通过后，再做单点联动（此命令会写 REG06 并在结束后尝试恢复）
python -m scripts.fullflow.case_saw_pn_sweep_1param --check-point
```

默认 `TEST_MODE` 沿用原程序 `FULL_SWEEP`。**不要不带 `--plan` 或 `--check-point` 就运行 Case**，否则将启动真正的自动扫描。也不要使用 `--no-restore`，除非明确希望保留最后工作点。

## 4. 输出及保存逻辑

保持 `outputs/fullflow/case_saw_pn_sweep_Nparam/run_YYYYMMDD_HHMMSS/` 与 `merged/`, `summary/`, `screenshots/`, `traces/`，以及 `summary_ibias_swcap_indcap.csv/.xlsx`、`all_traces_long.csv`、`run_plan.json`、`run_result.json`、`initial_register_snapshot.json`、`final_register_snapshot.json`、`register_comparison.json`、`run_log.txt`。汇总 Excel 保留 `Data`, `Original_Summary`, `Fixed_*`, `Optimization_Top30`, `Test_Info` 等分析页，寄存器列名按新芯片变为 `REG07/REG05/REG06`。

## 5. 保留旧串联谐振脚本的说明

为了保持原工程文件结构与历史代码，你之前的 `case_ibias_swcap_indcap_pn_sweep_v3/v4/v5...py` 及某些串联谐振教学、预设测试 Case **仍保留在工程里，但未作为并联芯片测试入口迁移，也未经本次并联芯片实机验证**。这些脚本包含旧 `CFG_OSC2_*`、`REG20–REG22` 地址，请**不要对并联芯片运行它们**。迁移版当前正式支持的扫描入口是以上 `case_saw_pn_sweep_1param.py`、`2param.py`、`3param.py`。以后若需迁移某个旧 Case，应先单独确认其目标 Field 与业务作用，不能把旧 `GMP_NUM` 等字段随意替换成新芯片的其他功能。

另外，通用 `main.py` 支持原始地址读写，**并未全局禁止用户访问无效寄存器地址**；确认芯片地址后，只使用文档列出的 REG05–REG14。

## 6. 离线自动回归结果

- 寄存器 Excel 重建：16/16 个寄存器参考值一致；35 个 Field；未发现位掩码冲突。
- 原工程两帧 SPI 协议保留：`0x00 addr` → `0x80 0x00` 读取第二帧 RX[1]，或 `0x00 addr` → `0x40 data` 写入。
- 1Param 5 组、2Param 12 组、3Param 48 组模拟扫描：完整 PASS。
- 仅写各自扫描的 REG，其他地址无数据写入；IND_P=N；保留所有非目标位。
- 全量快照：16/16 个寄存器初值与最终值相符，回读失败时扫描被阻止，非目标 REG 意外变化时报告错误。
- 原有 20 张 Excel 图表与数据导出在模拟运行中能够生成。
- SPI Mock/CLI/迁移回归：`python -m unittest tests.test_spi_read_protocol_mock tests.test_spi_cli_enhancements_mock tests.test_parallel_migration_offline -v`，37 项 PASS。

> 硬件未连接：不能声称 Ginkgo 真实收发、E5052B SCPI 实际通信、振荡器真实起振或仪器采样结果已验证。这些需要用户按步骤 D、E、F 实机执行并提供 LOG 后确认。
