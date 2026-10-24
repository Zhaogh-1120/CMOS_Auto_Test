# SPI Register Access Enhancement (2026-10-22)

本次更新集中于 Ginkgo USB-SPI 寄存器调试功能，保留既有 E5052B 相位噪声测试和 full-flow 工程结构。

## 主要变化
- 修正 SPI 读取：先用独立帧 `00 [addr]` 设置芯片内部地址，再用 `80 00` 读取，返回值取 `raw_rx[1]`。
- 新增统一只读命令：`read --reg 0x20`、`read --name REG20` 和 `read --name FIELD_NAME`。
- REG、Field 的写入及扫描支持 DEC、`0x` HEX、`0b` BIN 输入。
- 增加寄存器位宽、字段位宽和扫描范围预检查。
- 新增 `--dry-run` 预览修改结果（不发送寄存器数据写入命令）。
- 读取输出统一显示 `value_hex`、`value_bin=2b...`、`value_dec`；更新终端黄色读取值与红色错误提示。
- 新增两套子工程的离线 SPI 模拟测试及使用说明。

## 兼容性
- `write`、`write-read`、`sweep`、`field-read`、`field-write`、`field-write-read`、`field-sweep` 等原命令仍可使用。
- 保持现有 Ginkgo DLL、E5052B 核心测量代码和寄存器 JSON 文件不变。
- `--dry-run` 会读取芯片寄存器，不意味着完全没有 SPI 通信。

## 使用示例
```bat
cd full_flow_test
python main.py read --reg 0x20
python main.py read --name REG20
python main.py read --name CFG_OSC2_IDAC_IBIAS
python main.py field-write --name CFG_OSC2_IDAC_IBIAS --value 0b01010 --dry-run
python main.py field-sweep --name CFG_OSC2_IDAC_IBIAS --start 0 --stop 10 --step 2 --dry-run
python -m unittest discover -s tests -p "test_*mock.py" -v
```

## 验证状态与局限
- 离线：`full_flow_test` 33/33，`python_ginkgo_spi` 33/33 mock 测试通过。
- 已由用户在硬件上验证基础两帧读取，但本次未完成所有扫描与 E5052B 端到端回归。
- **已知问题尚未修复**：回读 FAIL 退出码/扫描继续、Field 全 REG 校验不足、`--use-shadow` 覆盖风险、批量部分写入、初始化资源释放、SPI 参数预检与扫描终点语义不一致。参见同包 `CHANGELOG_20261022.md`，建议后续单独修复。
