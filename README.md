# CMOS Auto-Test Monorepo

这个仓库建议按 3 个版块管理历史版本，便于追溯、复用和后续扩展：

1. `python_ginkgo_spi/`：Ginkgo + Python 与 CMOS 芯片进行 SPI 通信，包含整寄存器/字段读写、循环扫描、模板脚本。
2. `e5052b_capture/`：E5052B 图像与数据抓取相关代码，单独维护，便于后续替换仪器驱动。
3. `full_flow_test/`：把 SPI 配置、E5052B 采集、结果保存整合为全流程自动化测试。

## 推荐仓库使用方式

- 把**稳定可复用的底层能力**沉淀到 `python_ginkgo_spi/`。
- 把**仪器相关代码**单独收敛到 `e5052b_capture/`。
- 把**具体实验流程**写在 `full_flow_test/` 里，避免和底层通信耦合。
- 每次功能节点完成后提交一次 commit，commit message 直接描述：
  - `spi: add field-write-read verification`
  - `e5052b: add screenshot capture placeholder`
  - `flow: add spi + e5052b orchestrator skeleton`

## 目录概览

```text
CMOS_Auto_Test/
├─ python_ginkgo_spi/
├─ e5052b_capture/
├─ full_flow_test/
├─ docs/
├─ README.md
└─ .gitignore
```

详细建议见 `docs/ARCHITECTURE.md`。
