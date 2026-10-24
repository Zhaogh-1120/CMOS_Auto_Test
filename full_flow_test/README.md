# Full Flow Test — Parallel SAW Oscillator

`full_flow_test/` 负责组合 Ginkgo USB-SPI 与 Keysight E5052B，执行并联谐振 SAW 振荡器的自动化测试。

## 1. 环境

- Windows + Python（推荐使用独立 Conda 环境）。
- 已安装并能正常识别 Ginkgo USB-SPI 的 Windows 驱动 / DLL。
- E5052B 与电脑网络可通信，采集配置见 `config/instrument/e5052b_config.json`。

在 **`full_flow_test`** 目录运行：

```bat
python -m pip install -r requirements.txt
```

## 2. SPI 协议与寄存器映射

- 写 REG：先发送地址帧 `00 [addr]`，再发送数据帧 `40 [value]`。
- 读 REG：先发送地址帧 `00 [addr]`，再发送读取帧 `80 00`；使用第二帧返回数据的第二字节作为读值。
- 两帧各 16 个 SPI 时钟，CS 低有效；以当前已验证的硬件时序和驱动设置为准。
- 有效地址：REG05–REG14（16 个 REG / 35 个 Field）。
- SWCAP：`CFG_OSC_SWCAP` → REG05[3:0]。
- IND_CAP_N/P：`CFG_OSC_IND_SWCAP_N` → REG06[5:3]；`CFG_OSC_IND_SWCAP_P` → REG06[2:0]。
- IBIAS：`CFG_OSC_IDAC_IBIAS` → REG07[4:0]。

在自动化扫描 Case 中，IND_CAP_N 和 IND_CAP_P 同步（P=N）。通用 `main.py field-write` 不会自动为所有 Field 应用此耦合约束。

## 3. SPI 基础命令（Windows CMD）

```bat
python main.py field-list
python main.py read --reg 0x05
python main.py read --name REG05
python main.py field-read --name CFG_OSC_SWCAP
python main.py write-read --reg 0x05 --value 0x08
python main.py field-write-read --name CFG_OSC_SWCAP --value 10
python main.py field-write-read --name CFG_OSC_IDAC_IBIAS --value 15
python main.py field-sweep --name CFG_OSC_SWCAP --start 0 --stop 15 --step 3
```

`write-read` 会覆盖整个 REG；`field-write-read` 应仅修改目标位并保留其他位。上述含写入的命令会真实修改芯片寄存器，且单条 `main.py` 命令不保证自动恢复初值。

全寄存器只读检查：

```bat
python -m scripts.fullflow.parallel_spi_readonly_check
python -m scripts.fullflow.parallel_spi_readonly_check --read
```

## 4. 三套扫描 Case

| Case | 扫描对象 | 默认扫描码 | 组合数 |
| --- | --- | --- | ---: |
| 1Param | IND_CAP | 0, 2, 4, 6, 7 | 5 |
| 2Param | IBIAS × IND_CAP | IBIAS: 0, 6, 12, 15; IND_CAP: 0, 4, 7 | 12 |
| 3Param | IBIAS × SWCAP × IND_CAP | IBIAS: 0, 15, 30, 31; SWCAP: 0, 7, 14, 15; IND_CAP: 0, 4, 7 | 48 |

扫描模板中的范围规则强制包含起止点。未参与扫描的寄存器字段以启动时真实读回值为准，不发送默认初始化命令。

### 离线计划（不连接硬件）

```bat
python -m scripts.fullflow.case_saw_pn_sweep_1param --plan
python -m scripts.fullflow.case_saw_pn_sweep_2param --plan
python -m scripts.fullflow.case_saw_pn_sweep_3param --plan
```

### 硬件单点验证（会写寄存器并测量）

```bat
python -m scripts.fullflow.case_saw_pn_sweep_1param --check-point
python -m scripts.fullflow.case_saw_pn_sweep_2param --check-point
python -m scripts.fullflow.case_saw_pn_sweep_3param --check-point
```

### 完整扫描（会执行全部测量）

```bat
python -m scripts.fullflow.case_saw_pn_sweep_1param --run
python -m scripts.fullflow.case_saw_pn_sweep_2param --run
python -m scripts.fullflow.case_saw_pn_sweep_3param --run
```

执行前编辑相应 Case 源码开头的 `USER TEST CONFIGURATION`；无参数运行时默认采用 `TEST_MODE` 指定的模式。

## 5. E5052B 采集与结果

自动化 Case 依次执行寄存器写入/回读、Settle 等待、E5052B 相噪采集、结果导出、寄存器恢复与最终快照比较。仪器频率列保存原始读取的 Hz 数值，无法仅通过增加 Excel 显示位数提高实际频率分辨率。

默认输出目录：

```text
outputs/fullflow/case_saw_pn_sweep_2param/run_YYYYMMDD_HHMMSS/
├── screenshots/                # 每点 E5052B PNG 截图
├── traces/                     # 每点 PN CSV
├── summary/                    # 每点 Excel
├── merged/
├── summary_ibias_swcap_indcap.csv
├── summary_ibias_swcap_indcap.xlsx
├── all_traces_long.csv
├── pn_comparison.xlsx          # 新增相噪比较报告
├── initial_register_snapshot.json
├── final_register_snapshot.json
├── register_comparison.json
├── run_plan.json
├── run_result.json
└── run_log.txt
```

`pn_comparison.xlsx` 包括 `Overview`（最后一列嵌入原始 PNG）、`PN_Gallery`、`PN_Overlay`、`Raw_PN`、`Test_Info` 等页面。原有汇总 Excel 保留不变。某工作点截图失败或仪器读数无效时，依照对应 Case 的失败策略处理，不应把缺失数据视为测量 PASS。

重新使用旧数据生成 PN 对比报告（不连接硬件）：

```bat
python -m utils.pn_comparison_report --run-dir "outputs/fullflow/case_saw_pn_sweep_2param/run_YYYYMMDD_HHMMSS"
```

将示例的 `run_YYYYMMDD_HHMMSS` 替换为实际存在的测试目录。

## 6. 注意事项

- 三套 Case 只在结束或失败时尽力恢复实际写过的寄存器，并执行读取核对；断电、进程强制终止等情况下不能保证恢复。
- REG06 联动时应保留非目标 bit[7:6]。
- 真实 E5052B 测量等待时长需要覆盖仪器扫描/平均时间。
- Windows 输出路径尽量简短；深层目录可能导致截图或 CSV 创建失败。
- 公开仓库中不得提交未经允许的芯片设计资料、账号密钥和实验室专用配置。
