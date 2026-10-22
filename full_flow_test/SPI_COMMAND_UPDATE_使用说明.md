# SPI 寄存器命令更新说明（2026-10-22）

适用目录：`CMOS_Auto_Test-main/full_flow_test`；`python_ginkgo_spi` 目录也同步更新。

## 与上版兼容性

- 不改变已在芯片上验证通过的 SPI 读时序：CS 帧 1 发送 `00 [addr]` 设置地址；CS 帧 2 发送 `80 00`，取第二个 RX 字节作为数据。默认 SPI Mode 0、MSB First、500 kHz 保持不变。
- 不改变原有的 `write`、`write-read`、`sweep`、`field-write`、`field-write-read`、`field-sweep` 和 `field-read` 命令名称与基本输出。
- 不在启动时写入任何芯片初始化值。
- 命令行的目标数据及扫描边界均支持十进制（`10`）、十六进制（`0x0A`）、二进制（`0b01010`）。**二进制输出使用你指定的 `2b` 前缀，不能将其作为输入。**
- `REG20` 表示地址十六进制 `0x20`，`REG2A` 表示地址 `0x2A`，`REGFF` 表示地址 `0xFF`。`--reg 32`、`--reg 0x20` 等价。

## 1. 统一读取（都不会写入寄存器数据）

```powershell
python main.py read --reg 0x20
python main.py read --name REG20
python main.py read --name CFG_OSC2_IDAC_IBIAS
```

- 完整 REG 输出：`name=REG20`、`reg=0x20`、`raw_rx`、`read=0xXX`、`value_hex=0xXX value_bin=2bXXXXXXXX value_dec=NNN`，数值固定按 **HEX → BIN → DEC** 排列（`read=` 保留供旧命令使用）。通过 `--reg` 选地址也会自动展示 `name=REGxx`。
- Field 输出：`name=FIELD_NAME`、寄存器原值 `reg=0xXX`、`value_hex`、`value_bin`、`value_dec`，也按 **HEX → BIN → DEC** 排列。二进制按字段有效位宽补零。
- 终端高亮：读操作的 `name=...`、`read=...`、`value_hex/bin/dec=...` 使用**黄色**；Field 的 `reg=...` 沿用黄色，地址及 `raw_rx` 保持默认颜色；错误信息中的 `error:` 和之后的说明使用**红色**，前面的 `usage:` 仍保持默认颜色。设置环境变量 `NO_COLOR=1` 可关闭彩色输出。
- 仍支持原有命令：`python main.py field-read --name CFG_OSC2_IDAC_IBIAS`。
- 使用 `--reg` 与 `--name` 必须二选一，不允许同时使用。

## 2. 三种进制写入

下列三条 REG 命令写入数值相同（十进制 10）：

```powershell
python main.py write-read --reg 0x20 --value 10
python main.py write-read --reg 0x20 --value 0x0A
python main.py write-read --reg 0x20 --value 0b00001010
```

下列三条 Field 命令写入字段数值相同（十进制 10）：

```powershell
python main.py field-write-read --name CFG_OSC2_IDAC_IBIAS --value 10
python main.py field-write-read --name CFG_OSC2_IDAC_IBIAS --value 0x0A
python main.py field-write-read --name CFG_OSC2_IDAC_IBIAS --value 0b01010
```

注意：**上面是真实芯片写入命令**。在实测时请优先执行下一节的 `--dry-run`。

## 3. dry-run（真实读取 + 计算预览，无寄存器数据写入）

```powershell
python main.py write --reg 0x20 --value 0x54 --dry-run
python main.py field-write --name CFG_OSC2_IDAC_IBIAS --value 10 --dry-run
python main.py field-write-read --name CFG_OSC2_GMP_NUM --value 5 --dry-run
python main.py sweep --reg 0x20 --start 0b0 --stop 0x06 --step 2 --dry-run
python main.py field-sweep --name CFG_OSC2_IDAC_IBIAS --start 0 --stop 10 --step 2 --dry-run
```

示例输出（假设芯片真实 REG20 = `0x7C`，Field 高 5 bit 从 15 改为 10）：

```text
DRY_RUN  name=CFG_OSC2_IDAC_IBIAS  reg=0x20  field_value=10  before_reg=0x7C  after_reg=0x54  after_bin=2b01010100  status=NO_REGISTER_WRITE
```

工作方式：先以正常协议读取一次真实的目标寄存器，计算新值，在终端显示。**不会发送 Write Data 命令 `40 [data]`**，也不会运行 E5052B 扫描。地址设置帧 `00 [addr]` 仍会正常发送，它只更新内部地址指针，不写寄存器数据。

扫描 `--dry-run` 只读取一次扫描寄存器，全部预览点基于这一次的真实快照，且保持其他 Field 的位不变。预览后真正写入时会重新读取真实值，因此预览不是后续写入的锁定状态。

为了防止使用缓存而产生误导，`--dry-run` 不支持与 `--use-shadow` 同时使用。

## 4. 输入范围检查

- REG 地址：`0x00`–`0xFF`，超出会报错。
- 整体 REG 数据：0–255。比如 `0x100`、`-1` **会报错，不会被截断成 8-bit 再写入**。
- Field 数据：必须在该 Field 的 `0..max_decimal` 范围内，如 `CFG_OSC2_IDAC_IBIAS` 的 5-bit 范围为 0–31，`CFG_OSC2_GMP_NUM` 的 3-bit 范围为 0–7。
- 扫描起点、终点都要在有效范围内；步长不得为 0，且方向必须正确。先验证整段扫描范围再打开 SPI 设备。
- 出现参数校验错误时，在发送任何 SPI 命令前终止执行。

上述边界检查也增加到 `ChipSpi` 底层 API，因此 Python 脚本直接调用 `write_reg`、`write_field`、`sweep_reg`、`sweep_field` 时同样受保护。

## 5. 离线单元测试（不接仪器、不加载 Ginkgo DLL）

在 VS Code 的工作目录 `full_flow_test`（或 `python_ginkgo_spi`）运行：

```powershell
python -m unittest discover -s tests -p "test_*mock.py" -v
```

两套目录各 29 项，原有 SPI 两帧读法测试及新增功能测试全部通过。使用内存模拟 Ginkgo 设备，并不等价于实体芯片已验证。

## 6. 推荐的实物验证顺序

只读：

```powershell
python main.py read --name REG20
python main.py read --name CFG_OSC2_IDAC_IBIAS
python main.py read --reg 0x21
```

无写入预演：

```powershell
python main.py field-write --name CFG_OSC2_IDAC_IBIAS --value 0b01010 --dry-run
```

确认预测的 REG 值符合预期后，再执行你允许的实际写入。若芯片存在 W1C、动态状态位或其他特殊语义，应先确认相应寄存器支持常规读改写操作。
