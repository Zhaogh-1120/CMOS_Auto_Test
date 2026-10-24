# register_excel_to_json_minimal.py 使用说明

## 1. 脚本用途

这个脚本用于将你现在使用的**最小输入版寄存器模板 Excel**，自动转换成工程迁移所需的两个配置文件：

- `register_fields.json`
- `registers.json`

同时会额外生成一个检查用文件：

- `conversion_report.md`

适用于以下场景：

- 后续更换芯片项目
- SPI 通信协议保持不变
- 仅寄存器名称、地址、默认值、字段位宽发生变化
- 需要快速把新的寄存器表迁移到现有自动化测试工程中

---

## 2. 对应的 Excel 模板

这个脚本适配的是你现在这版**最小输入模板**，不是旧模板。

模板中重点会用到两个工作表：

### （1）`字段输入模板`
这是主要填写页。

建议至少填写以下列：

- `register_name`
- `field_base_name`
- `bit_spec`
- `default_decimal`

可选填写：

- `alias`
- `access`
- `description`
- `notes`

其中：

- `bit_spec` 可写成 `7:3` 或 `2`
- `default_decimal` 是该字段的默认十进制值

### （2）`可选_寄存器汇总`
这个表用于提供寄存器地址映射。

建议至少填写：

- `register_name`
- `address_decimal`

脚本会根据 `register_name` 自动把地址匹配到字段表中。

---

## 3. 自动计算内容

你不需要手工填写以下内容，脚本会自动生成：

- `msb`
- `lsb`
- `bits`
- `width`
- `mask`
- `max_decimal`
- `field_full_name`
- `address_hex`

同时脚本会自动按字段默认值拼接整寄存器默认值，并写入 `registers.json`。

---

## 4. 输出文件说明

运行完成后，会生成以下文件：

### `register_fields.json`
字段级映射表，供字段读写、字段扫描等功能使用。

通常包含：
- 字段名称
- 别名
- 地址
- 位段
- 默认值
- mask
- 最大值等信息

### `registers.json`
寄存器级汇总表，供寄存器初始化、默认值恢复、寄存器映射检查使用。

通常包含：
- 寄存器名
- 寄存器地址
- 默认寄存器值
- 地址十六进制表示等信息

### `conversion_report.md`
转换报告，用来人工检查：
- 每个寄存器由哪些字段组成
- 每个字段默认值是多少
- 最终拼出的寄存器默认值是多少

建议每次迁移工程后都看一眼这个报告。

---

## 5. 最常用命令

假设你的 Excel 文件名为：

`寄存器迁移模板_AutoTest_最小输入版.xlsx`

并希望输出到工程目录：

`config/active`

则运行：

```bash
python register_excel_to_json_minimal.py 寄存器迁移模板_AutoTest_最小输入版.xlsx --out-dir config/active
```

运行成功后，会在 `config/active` 下生成：

- `register_fields.json`
- `registers.json`
- `conversion_report.md`

---

## 6. 推荐使用流程

### 第一步：准备 Excel
在 `可选_寄存器汇总` 中填写：
- `register_name`
- `address_decimal`

在 `字段输入模板` 中填写：
- `register_name`
- `field_base_name`
- `bit_spec`
- `default_decimal`

### 第二步：运行脚本
在工程根目录或脚本所在目录执行：

```bash
python register_excel_to_json_minimal.py 你的模板.xlsx --out-dir config/active
```

### 第三步：检查输出结果
重点检查：
- `register_fields.json`
- `registers.json`
- `conversion_report.md`

### 第四步：替换工程配置
把新生成的两个 json 文件放入你的工程配置目录中，用于后续字段读写和扫描。

---

## 7. bit_spec 填写规则

### 单 bit
例如：

```text
2
```

表示：
- `msb = 2`
- `lsb = 2`

### 多 bit
例如：

```text
7:3
```

表示：
- `msb = 7`
- `lsb = 3`

脚本会自动计算：
- `width = 5`
- `mask = 0b11111000 = 248`

---

## 8. 脚本会做的检查

脚本会自动检查一些常见问题，例如：

- `register_name` 为空
- `field_base_name` 为空
- `bit_spec` 格式错误
- `default_decimal` 超出字段允许范围
- 同名寄存器出现地址冲突
- 同一寄存器内字段位段是否异常

如果表格内容明显不合理，脚本会报错，便于你及时修正。

---

## 9. 迁移时建议

为了保证迁移稳定，建议你以后都按同一种格式维护寄存器表：

- 寄存器地址统一在 `可选_寄存器汇总` 中维护
- 字段信息统一在 `字段输入模板` 中维护
- 字段默认值尽量使用十进制填写
- `bit_spec` 统一使用 `msb:lsb` 或单 bit 数字格式
- 字段名尽量保持稳定、清晰、唯一

这样以后换项目时，只需要：
1. 填新的 Excel
2. 跑一次转换脚本
3. 替换配置文件

基本不用再手工改 Python 工程里的寄存器映射逻辑。

---

## 10. 一个典型例子

假设你填写：

### `可选_寄存器汇总`

| register_name | address_decimal |
|---|---:|
| REG20 | 32 |

### `字段输入模板`

| register_name | field_base_name | bit_spec | default_decimal |
|---|---|---|---:|
| REG20 | GMP_NUM | 2:0 | 5 |
| REG20 | BUF_EN | 3 | 1 |

脚本会自动得到：

- `GMP_NUM` 占用 bit `[2:0]`
- `BUF_EN` 占用 bit `[3]`
- `REG20` 地址为 `32`
- `REG20` 默认值按字段拼接后自动算出

---

## 11. 建议放置位置

建议把这个脚本放在工程中的工具目录，例如：

```text
tools/register_excel_to_json_minimal.py
```

或者放在：

```text
protocol/register_excel_to_json_minimal.py
```

便于后续版本管理与 GitHub 上传。

---

## 12. 总结

以后你的工程迁移流程可以固定为：

1. 新项目寄存器按最小输入模板整理
2. 运行 `register_excel_to_json_minimal.py`
3. 生成新的 `register_fields.json` 和 `registers.json`
4. 替换工程配置
5. 继续使用原有 SPI 协议和自动化测试框架

这样可以最大限度减少后续不同芯片项目之间的迁移成本。
