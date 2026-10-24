# CMOS_Auto_Test

基于 **Ginkgo USB-SPI** 和 **Keysight E5052B** 的 CMOS / SAW 振荡器自动化测试工程，包含寄存器读写、嵌套参数扫描、相位噪声采集与 Excel 报告。

## 项目结构

| 目录 | 作用 |
| --- | --- |
| `python_ginkgo_spi/` | Ginkgo SPI 底层通信与独立示例 |
| `e5052b_capture/` | E5052B 采集相关独立工具 |
| `full_flow_test/` | SPI + E5052B 联合测量、扫描 Case、分析报告 |
| `docs/` | 通用开发文档 |

> 当前 `full_flow_test/` 的默认寄存器映射针对**并联谐振 SAW 振荡器**。若切换至其他芯片，必须核实 Field 名称、寄存器地址与 bit 映射，不能直接复用当前写入配置。

## 主要功能

- 通过 REG 地址、REG 名称或 Field 名称执行 SPI 读写、写后回读与扫描；支持十进制、十六进制、二进制输入。
- 并联 SAW 芯片寄存器映射：**REG05–REG14（16 个寄存器，35 个 Field）**。
- 启动时读取芯片真实寄存器快照，不默认初始化；测试结束后尝试恢复已写入寄存器，并对全部有效寄存器进行前后比较。
- `IND_CAP_P`、`IND_CAP_N` 在自动扫描 Case 中联动，保证 **P=N**。
- 1Param、2Param、3Param 嵌套扫描模板（扫描起止点包含末端值）。
- E5052B 相位噪声、载波频率、功率、Jitter、原始曲线和仪器截图采集。
- 自动导出 CSV、原始 PNG、单点 Excel、汇总 Excel 和 `pn_comparison.xlsx`；后者包含 Overview 中逐行嵌入的原始 PNG、相噪曲线叠加及原始数据。

## 快速开始（Windows CMD）

在具备相应 Windows Ginkgo 驱动、仪器连接和 Python 依赖的计算机上：

```bat
cd full_flow_test
python -m pip install -r requirements.txt
python main.py field-list
python -m scripts.fullflow.parallel_spi_readonly_check
python -m scripts.fullflow.parallel_spi_readonly_check --read
```

**注意：** `--read` 会连接真实 SPI 设备；仅执行不带 `--read` 的映射检查不会进行硬件读写。

扫描脚本建议先执行不连接硬件的 `--plan`：

```bat
python -m scripts.fullflow.case_saw_pn_sweep_1param --plan
python -m scripts.fullflow.case_saw_pn_sweep_2param --plan
python -m scripts.fullflow.case_saw_pn_sweep_3param --plan
```

确认计划后，使用 `--check-point` 进行单点硬件验证，或使用 `--run` 执行完整扫描。**`--run` 会连接设备并修改扫描目标寄存器。**

详细命令、寄存器定义和输出目录见 [full_flow_test/README.md](full_flow_test/README.md)。

## 版本与说明

- [CHANGELOG.md](CHANGELOG.md)：历史更新记录。
- [并联 SAW 迁移与验证](README_PARALLEL_SAW_%E8%BF%81%E7%A7%BB%E4%B8%8E%E9%AA%8C%E8%AF%81.md)：并联芯片使用说明。

## 使用与数据安全

- 确认寄存器映射与真实硬件一致后再执行任何写入操作。
- `outputs/`、`logs/`、测试截图和现场配置不应作为源代码常规提交。
- 仓库公开发布前应检查是否包含未获授权披露的芯片寄存器信息、实验室 IP、凭据或第三方驱动文件。
- 实测频率精度由仪器返回数据决定；Excel 增加显示位数不等于提高真实测量分辨率。
