# SPI 离线审计复现脚本

在已解压的 Enhanced_Color 工程的 `full_flow_test` 或 `python_ginkgo_spi` 目录打开 Windows CMD，先执行：

```cmd
set SPI_AUDIT_PROJECT=%CD%
```

假设将压缩包里的 `.py` 脚本解压到 `C:\spi_audit_tools`，运行：

```cmd
python C:\spi_audit_tools\audit_ext_tests.py -v
python C:\spi_audit_tools\repro_findings.py
```

在 `full_flow_test` 中额外运行：

```cmd
python C:\spi_audit_tools\repro_session.py
```

- `audit_ext_tests.py`：8 项新增正常/边界/随机功能验证；完全模拟 Ginkgo SPI。
- `repro_findings.py`：7 类故障路径/设计缺陷的**重现**；若输出 ALL 7 ISSUES REPRODUCED 表示目前的缺陷被复现，不代表测试程序没有缺陷。
- `repro_session.py`：单独复现 FullFlowRecord 的 SPI FAIL/overall PASS 状态不一致。

**不会连接设备，也不会写入实物芯片。** 这些脚本不会更新工程源码。不同 Python 环境中可能需要安装主工程已有依赖，特别是完整流程 `repro_session.py` 所导入的工具模块。
