# SPI 寄存器直接读取修复说明（2026-10-22）

## 修复原因

原 `protocol/chip_spi.py::read_reg_raw()` 发送 `[0x80, reg_addr]`，但芯片当前使用的 SPI RTL 中，`0x80` 属于 Read Data，**不是携带地址的读取命令**。从机依据内部保存的 `addr` 选择读取哪一个 page。此前执行 `write_reg()` 会预先设置 `addr`，因此“先写后读”常常成功，而上电后的直接读取却总返回 `0x00`。

## 实际改动

`read_reg_raw(reg_addr)` 现在会顺序执行：

1. `transfer([address_cmd, reg_addr])`，默认 `address_cmd=0x00`（原工程已经成功用于写入的 Set Address 指令）
2. 当前帧结束，CS 释放为高电平；下一次 API 调用重新拉低 CS
3. `transfer_read([read_cmd, 0x00], rx_len=2)`，默认 `read_cmd=0x80`。第二字节 `0x00` 只是产生读取 SCK 时钟的 dummy，**不是地址，也不是 Write Data**
4. `decode_read_value(rx)`，默认取 `rx[1]` 为寄存器真实数据

本次没有修改 `driver/control_spi.py`、SPI 模式或速率；保留先前测试通过的 Ginkgo API 用法和 CS 帧划分。没有添加初始化寄存器写入。`write_reg()` 的 `[00 addr]`、`[40 data]` 写操作保持原样。

若希望测试另一份文档建议的 Set Address 命令 `0x1F`，可以在命令行末尾加 `--address-cmd 0x1F`。该选项只存在于 `main.py` CLI；直接使用 `ChipSpi()` 时，可用 `ChipSpi(ChipSpiConfig(address_cmd=0x1F))`，**没有实物验证之前请不要同时更改多个设置**。

## VS Code 终端验证（先进入 full_flow_test 目录，已激活原有 Python 虚拟环境）

**请先执行只读测试，不执行写入/扫描测试：**

```powershell
python main.py read --reg 0x20
python main.py read --reg 0x21
python main.py field-read --name CFG_OSC2_GMP_NUM
```

或者运行：

```powershell
python -m tests.read_only_check --reg 0x20
```

如果使用 `python_ginkgo_spi`，也进入其目录执行相同命令。

预期第二条 SPI 帧的 MOSI 为 `80 00`，MISO 收到的第二字节是回读值。`raw_rx[0]` 是读命令期间的接收内容，不应作为寄存器值。

继续排查时可做对照测试：

```powershell
python main.py read --reg 0x20 --address-cmd 0x1F
```

这不是强制设置默认值，而是提供替代 Set Address 编码的实验手段。若连续读取不同地址总返回相同的值，请使用逻辑分析仪确认各帧 CS 高电平间隔（参考文档 >95 ns）、CPOL/CPHA、SDO 接线、接收缓冲长度和 `page_00_00` 访问门控。不要把 SPI 读取返回 `0x00` 自动判定为失败，因为寄存器实际值也可能是零。

## 脱机协议回归测试（无需接入仪器或加载 Windows DLL）

```powershell
python -m unittest tests.test_spi_read_protocol_mock -v
```

这会检查：直接读取是否先设置地址、发送的 dummy 是否为 `0x00`、读字段是否只读、写字段是否保留其他位、写后读是否正确、寄存器切换时是否重新设置地址、传输错误能否被报告。

## 注意

- 此次验证的只是代码层面的协议时序；尚未实际连接你的 Ginkgo 控制器及芯片，实际成功与否需要硬件验证。
- `--use-shadow` 表示使用软件镜像计算待写寄存器值，不保证芯片上电真实值；如想保留芯片其他 bit 的真实状态，**不要使用** `--use-shadow`。
- 测试前请确认目标寄存器属于可读范围，`page_00_00` 的访问使能条件符合芯片规格。
- 若是针对不同版图/芯片修订版本，优先用对应 RTL 校对地址、默认值和门控行为。
