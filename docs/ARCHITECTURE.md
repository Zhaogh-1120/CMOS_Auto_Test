# Repository Architecture

## 1. python_ginkgo_spi

定位：**底层 SPI 通信能力库**。

建议职责：
- Ginkgo 设备驱动调用
- SPI 参数配置
- 整寄存器读写
- 字段读写
- 写后读回验证
- 通用扫描模板

不建议放：
- E5052B 采集细节
- 某个实验的完整业务流程

## 2. e5052b_capture

定位：**仪器采集能力库**。

建议职责：
- 建立 VISA / SCPI 会话
- 抓图
- 导出 CSV / trace / screenshot
- 数据命名规则

## 3. full_flow_test

定位：**业务编排层**。

建议职责：
- 先配置 SPI
- 再抓取 E5052B
- 保存结果
- 记录 sweep 条件与输出路径

## 版本管理建议

- `main`：稳定可运行版本
- `dev`：日常开发分支
- `feature/spi-*`：SPI 通信相关功能
- `feature/e5052b-*`：仪器采集相关功能
- `feature/flow-*`：全流程测试相关功能
